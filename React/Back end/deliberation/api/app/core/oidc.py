from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any
from urllib.parse import urlencode

import requests
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from .auth_store import (
    authorize_and_bind_allowlist,
    authorize_password_user,
    authorize_shared_credential,
    consume_oidc_transaction,
    create_auth_session,
    create_oidc_transaction,
    keyed_hash,
    normalize_exact_email,
    record_auth_audit,
    revoke_auth_session,
)
from .access_users import authenticate_access_user
from .config import Settings, get_settings
from .errors import CONTRACT_VERSION, error_response
from .rate_limit import rate_limiter

router = APIRouter(tags=["authentication"])


class PasswordLoginIn(BaseModel):
    username: str = ""
    password: str = ""


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or "")


def _request_ip(request: Request) -> str:
    return str(request.client.host if request.client else "")


def _return_to(value: str | None) -> str:
    candidate = str(value or "/").strip() or "/"
    if (
        not candidate.startswith("/")
        or candidate.startswith("//")
        or "\\" in candidate
        or "\r" in candidate
        or "\n" in candidate
    ):
        raise ValueError("returnTo must be a same-origin relative path.")
    return candidate


def _provider_enabled(settings: Settings, provider: str) -> bool:
    return settings.auth_mode == "oidc" and provider == settings.oidc_provider


def _verify_shared_password(settings: Settings, password: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, expected_text = (
            settings.shared_password_hash.split("$", 3)
        )
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text + "=" * (-len(salt_text) % 4))
        expected = base64.urlsafe_b64decode(
            expected_text + "=" * (-len(expected_text) % 4)
        )
        derived = hashlib.pbkdf2_hmac(
            "sha256", str(password or "").encode("utf-8"), salt, iterations
        )
        return iterations >= 600_000 and secrets.compare_digest(derived, expected)
    except (TypeError, ValueError):
        return False


@router.post("/auth/login")
def password_login(request: Request, payload: PasswordLoginIn):
    settings = get_settings()
    request_id = _request_id(request)
    if settings.auth_mode != "password" or not settings.auth_secret_configured:
        return error_response(
            503,
            "PASSWORD_AUTH_NOT_CONFIGURED",
            "Staff sign-in is not configured.",
            request_id=request_id,
        )
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    if not origin or origin != settings.frontend_origin:
        return error_response(
            403,
            "ORIGIN_FORBIDDEN",
            "The request origin is not permitted.",
            request_id=request_id,
        )
    ip = _request_ip(request)
    allowed, retry_after = rate_limiter.allow(
        f"password-login:{ip}", limit=5, window_seconds=900
    )
    if not allowed:
        return error_response(
            429,
            "RATE_LIMITED",
            "Too many login attempts. Try again later.",
            request_id=request_id,
            retryable=True,
            headers={"Retry-After": str(retry_after)},
        )
    matched_email = None
    legacy_valid = False
    if settings.access_users_file:
        try:
            matched_email = authenticate_access_user(
                settings.access_users_file, payload.username, payload.password
            )
        except ValueError:
            matched_email = None
    else:
        expires_at = datetime.fromisoformat(
            settings.shared_credential_expires_at.replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        username_ok = secrets.compare_digest(
            str(payload.username or ""), settings.shared_username
        )
        password_ok = _verify_shared_password(settings, payload.password)
        legacy_valid = (
            expires_at > datetime.now(timezone.utc) and username_ok and password_ok
        )
    if not matched_email and not legacy_valid:
        record_auth_audit(
            settings,
            "login_failed",
            outcome="denied",
            provider="password",
            request_id=request_id,
            ip_address=ip,
            user_agent=request.headers.get("User-Agent", ""),
            reason_code="INVALID_OR_EXPIRED_CREDENTIAL",
        )
        return error_response(
            401,
            "AUTH_INVALID",
            "The username or password is incorrect.",
            request_id=request_id,
        )
    principal = (
        authorize_password_user(settings, matched_email)
        if matched_email
        else authorize_shared_credential(settings)
    )
    if principal is None:
        return error_response(
            503,
            "AUTH_STORE_UNAVAILABLE",
            "Staff sign-in is temporarily unavailable.",
            request_id=request_id,
            retryable=True,
        )
    raw_session_id, _, _ = create_auth_session(settings, principal)
    record_auth_audit(
        settings,
        "login_succeeded",
        outcome="success",
        provider="password",
        issuer="fs:access-users-file" if matched_email else "fs:shared-credential",
        subject=str(principal.get("subject") or ""),
        allowlist_id=str(principal.get("allowlistId") or ""),
        request_id=request_id,
        ip_address=ip,
        user_agent=request.headers.get("User-Agent", ""),
    )
    response = JSONResponse(
        status_code=200,
        content={"contractVersion": CONTRACT_VERSION, "authenticated": True},
    )
    response.set_cookie(
        settings.session_cookie_name,
        raw_session_id,
        max_age=settings.session_absolute_hours * 3600,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
        path="/",
    )
    return response


@lru_cache(maxsize=8)
def _metadata(issuer: str) -> dict[str, Any]:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    response = requests.get(url, timeout=12, headers={"Accept": "application/json"})
    response.raise_for_status()
    payload = response.json()
    if str(payload.get("issuer") or "").rstrip("/") != issuer.rstrip("/"):
        raise RuntimeError("OIDC discovery issuer mismatch.")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not str(payload.get(key) or "").startswith("https://"):
            raise RuntimeError("OIDC discovery endpoint is missing or not HTTPS.")
    return payload


@lru_cache(maxsize=8)
def _jwks(jwks_uri: str) -> dict[str, Any]:
    response = requests.get(jwks_uri, timeout=12, headers={"Accept": "application/json"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload.get("keys"), list):
        raise RuntimeError("OIDC JWKS response is invalid.")
    return payload


def _exchange_code(
    settings: Settings,
    *,
    code: str,
    verifier: str,
    redirect_uri: str,
    token_endpoint: str,
) -> str:
    response = requests.post(
        token_endpoint,
        timeout=15,
        headers={"Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
            "code_verifier": verifier,
        },
    )
    response.raise_for_status()
    payload = response.json()
    id_token = str(payload.get("id_token") or "")
    if not id_token:
        raise RuntimeError("OIDC token response did not contain an ID token.")
    return id_token


def _validate_id_token(
    settings: Settings,
    *,
    id_token: str,
    metadata: dict[str, Any],
    expected_nonce_hash: str,
) -> dict[str, Any]:
    try:
        from joserfc import jwt
        from joserfc.errors import JoseError
        from joserfc.jwk import KeySet
        from joserfc.jwt import JWTClaimsRegistry
    except ImportError as exc:  # pragma: no cover - startup dependency check
        raise RuntimeError("joserfc is required for OIDC validation.") from exc
    claims_options = {
        "iss": {"essential": True, "value": settings.oidc_issuer},
        "aud": {"essential": True, "value": settings.oidc_client_id},
        "exp": {"essential": True},
        "nbf": {"essential": False},
        "iat": {"essential": True},
        "sub": {"essential": True},
    }
    try:
        token = jwt.decode(
            id_token,
            KeySet.import_key_set(_jwks(str(metadata["jwks_uri"]))),
            algorithms=["RS256"],
        )
        JWTClaimsRegistry(leeway=60, **claims_options).validate(token.claims)
        claims = token.claims
    except (JoseError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("OIDC ID token validation failed.") from exc
    audience = claims.get("aud")
    authorized_party = str(claims.get("azp") or "")
    if isinstance(audience, (list, tuple)) and len(audience) > 1:
        if authorized_party != settings.oidc_client_id:
            raise ValueError("OIDC authorized party validation failed.")
    elif authorized_party and authorized_party != settings.oidc_client_id:
        raise ValueError("OIDC authorized party validation failed.")
    nonce = str(claims.get("nonce") or "")
    if not nonce or not secrets.compare_digest(
        keyed_hash(settings, "oidc-nonce", nonce), expected_nonce_hash
    ):
        raise ValueError("OIDC nonce validation failed.")
    provider = settings.oidc_provider
    if provider == "google":
        if claims.get("email_verified") is not True:
            raise ValueError("The organization email is not verified.")
        if str(claims.get("hd") or "").strip().lower() != settings.oidc_google_hosted_domain:
            raise ValueError("The organization domain is not permitted.")
        email = str(claims.get("email") or "")
    else:
        if str(claims.get("tid") or "").strip() != settings.oidc_entra_tenant_id:
            raise ValueError("The organization tenant is not permitted.")
        if not settings.oidc_entra_allow_guests:
            idp = str(claims.get("idp") or "").strip().rstrip("/")
            member_idps = {
                "",
                settings.oidc_issuer.rstrip("/"),
                f"https://sts.windows.net/{settings.oidc_entra_tenant_id}",
            }
            if idp not in member_idps:
                raise ValueError("Guest identities are not permitted.")
        email = str(
            claims.get("email")
            or claims.get("preferred_username")
            or claims.get("upn")
            or ""
        )
    if not email:
        raise ValueError("The provider did not return an organization email.")
    email = normalize_exact_email(email)
    if provider == "google" and email.rsplit("@", 1)[1] != settings.oidc_google_hosted_domain:
        raise ValueError("The organization email domain is not permitted.")
    return {
        "issuer": str(claims["iss"]),
        "subject": str(claims["sub"]),
        "email": email,
        "provider": provider,
    }


def _login_failure_redirect(settings: Settings) -> RedirectResponse:
    return RedirectResponse(
        url=f"{settings.frontend_origin}/auth/callback?error=login_failed",
        status_code=303,
    )


@router.get("/auth/login")
def oidc_login(
    request: Request,
    provider: str = Query(...),
    return_to: str = Query("/", alias="returnTo"),
):
    settings = get_settings()
    provider = str(provider or "").strip().lower()
    if not _provider_enabled(settings, provider) or not settings.oidc_configured:
        return error_response(
            503,
            "OIDC_NOT_CONFIGURED",
            "Organization login is not configured.",
            request_id=_request_id(request),
        )
    try:
        safe_return_to = _return_to(return_to)
    except ValueError:
        return error_response(
            400,
            "AUTH_RETURN_TO_INVALID",
            "The requested return location is invalid.",
            request_id=_request_id(request),
        )
    ip = _request_ip(request)
    allowed, retry_after = rate_limiter.allow(
        f"oidc-login:{ip}", limit=12, window_seconds=300
    )
    if not allowed:
        record_auth_audit(
            settings,
            "login_started",
            outcome="rate-limited",
            provider=provider,
            request_id=_request_id(request),
            ip_address=ip,
            user_agent=request.headers.get("User-Agent", ""),
            reason_code="RATE_LIMITED",
        )
        return error_response(
            429,
            "RATE_LIMITED",
            "Too many login attempts. Try again later.",
            request_id=_request_id(request),
            retryable=True,
            headers={"Retry-After": str(retry_after)},
        )
    try:
        metadata = _metadata(settings.oidc_issuer)
        state = secrets.token_urlsafe(36)
        nonce = secrets.token_urlsafe(36)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        create_oidc_transaction(
            settings,
            provider=provider,
            state=state,
            nonce=nonce,
            pkce_verifier=verifier,
            redirect_uri=settings.oidc_redirect_uri,
            return_to=safe_return_to,
        )
        record_auth_audit(
            settings,
            "login_started",
            outcome="started",
            provider=provider,
            issuer=settings.oidc_issuer,
            request_id=_request_id(request),
            ip_address=ip,
            user_agent=request.headers.get("User-Agent", ""),
        )
        query = urlencode(
            {
                "client_id": settings.oidc_client_id,
                "response_type": "code",
                "scope": "openid profile email",
                "redirect_uri": settings.oidc_redirect_uri,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "hd": settings.oidc_google_hosted_domain if provider == "google" else "",
            }
        )
        return RedirectResponse(
            url=f"{metadata['authorization_endpoint']}?{query}", status_code=307
        )
    except Exception:
        return error_response(
            503,
            "OIDC_PROVIDER_UNAVAILABLE",
            "Organization login is temporarily unavailable.",
            request_id=_request_id(request),
            retryable=True,
        )


@router.get("/auth/callback/{provider}")
def oidc_callback(
    request: Request,
    provider: str,
    code: str = Query(""),
    state: str = Query(""),
    error: str = Query(""),
):
    settings = get_settings()
    provider = str(provider or "").strip().lower()
    if not _provider_enabled(settings, provider) or not settings.oidc_configured:
        return error_response(
            503,
            "OIDC_NOT_CONFIGURED",
            "Organization login is not configured.",
            request_id=_request_id(request),
        )
    ip = _request_ip(request)
    user_agent = request.headers.get("User-Agent", "")
    if error or not code or not state:
        record_auth_audit(
            settings,
            "login_failed",
            outcome="denied",
            provider=provider,
            issuer=settings.oidc_issuer,
            request_id=_request_id(request),
            ip_address=ip,
            user_agent=user_agent,
            reason_code="PROVIDER_DENIED",
        )
        return _login_failure_redirect(settings)
    transaction = consume_oidc_transaction(settings, state, provider)
    if transaction is None:
        record_auth_audit(
            settings,
            "login_failed",
            outcome="denied",
            provider=provider,
            issuer=settings.oidc_issuer,
            request_id=_request_id(request),
            ip_address=ip,
            user_agent=user_agent,
            reason_code="STATE_INVALID_OR_REPLAYED",
        )
        return _login_failure_redirect(settings)
    try:
        metadata = _metadata(settings.oidc_issuer)
        id_token = _exchange_code(
            settings,
            code=code,
            verifier=str(transaction["pkceVerifier"]),
            redirect_uri=str(transaction["redirectUri"]),
            token_endpoint=str(metadata["token_endpoint"]),
        )
        identity = _validate_id_token(
            settings,
            id_token=id_token,
            metadata=metadata,
            expected_nonce_hash=str(transaction["nonceHash"]),
        )
        principal = authorize_and_bind_allowlist(settings, **identity)
        if principal is None:
            record_auth_audit(
                settings,
                "allowlist_denied",
                outcome="denied",
                provider=provider,
                issuer=identity["issuer"],
                subject=identity["subject"],
                request_id=_request_id(request),
                ip_address=ip,
                user_agent=user_agent,
                reason_code="ALLOWLIST_DENIED_OR_SUBJECT_MISMATCH",
            )
            return _login_failure_redirect(settings)
        raw_session_id, _, _ = create_auth_session(settings, principal)
        record_auth_audit(
            settings,
            "login_succeeded",
            outcome="success",
            provider=provider,
            issuer=identity["issuer"],
            subject=identity["subject"],
            allowlist_id=str(principal["allowlistId"]),
            request_id=_request_id(request),
            ip_address=ip,
            user_agent=user_agent,
        )
        response = RedirectResponse(
            url=f"{settings.frontend_origin}{transaction['returnTo']}", status_code=303
        )
        response.set_cookie(
            settings.session_cookie_name,
            raw_session_id,
            max_age=settings.session_absolute_hours * 3600,
            secure=settings.session_cookie_secure,
            httponly=True,
            samesite=settings.session_cookie_samesite,
            path="/",
        )
        return response
    except Exception:
        record_auth_audit(
            settings,
            "login_failed",
            outcome="denied",
            provider=provider,
            issuer=settings.oidc_issuer,
            request_id=_request_id(request),
            ip_address=ip,
            user_agent=user_agent,
            reason_code="TOKEN_OR_CLAIM_VALIDATION_FAILED",
        )
        return _login_failure_redirect(settings)


@router.get("/auth/me")
def auth_me(request: Request):
    principal = getattr(request.state, "principal", None)
    session = getattr(request.state, "auth_session", None)
    if not principal or not session:
        return error_response(
            401,
            "AUTH_SESSION_MISSING",
            "Authentication is required.",
            request_id=_request_id(request),
        )
    return {
        "contractVersion": CONTRACT_VERSION,
        "authenticated": True,
        "principal": principal,
        "session": {
            "issuedAt": session.get("issuedAt"),
            "lastSeenAt": session.get("lastSeenAt"),
            "idleExpiresAt": session.get("idleExpiresAt"),
            "absoluteExpiresAt": session.get("absoluteExpiresAt"),
        },
        "csrf": {
            "headerName": get_settings().csrf_header_name,
            "token": session.get("csrfToken"),
        },
    }


@router.post("/auth/logout")
def auth_logout(request: Request):
    settings = get_settings()
    session = getattr(request.state, "auth_session", None) or {}
    principal = getattr(request.state, "principal", None) or {}
    session_hash = str(session.get("sessionIdHash") or "")
    if session_hash:
        revoke_auth_session(session_hash)
    record_auth_audit(
        settings,
        "logout",
        outcome="success",
        provider=str(principal.get("provider") or ""),
        issuer=str(principal.get("issuer") or ""),
        subject=str(session.get("subject") or ""),
        allowlist_id=str(principal.get("principalId") or ""),
        request_id=_request_id(request),
        ip_address=_request_ip(request),
        user_agent=request.headers.get("User-Agent", ""),
    )
    response = JSONResponse(
        status_code=200,
        content={"contractVersion": CONTRACT_VERSION, "ok": True},
    )
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
    return response
