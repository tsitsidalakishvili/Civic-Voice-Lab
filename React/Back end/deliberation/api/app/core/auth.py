import secrets
from fnmatch import fnmatch
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from .auth_store import keyed_hash, load_auth_session, record_auth_audit
from .config import Settings, get_settings
from .errors import CONTRACT_VERSION, error_response
from .rate_limit import rate_limiter
from ..db import get_active_database, get_driver

router = APIRouter(tags=["platform"])


def _normalize_path(path: str) -> str:
    normalized = str(path or "").strip() or "/"
    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized.rstrip("/")
    return normalized or "/"


def _rule_matches(request: Request, rule: str) -> bool:
    method = request.method.upper()
    path = _normalize_path(request.url.path)
    rule_text = str(rule or "").strip()
    if not rule_text:
        return False
    if ":" in rule_text:
        rule_method, pattern = rule_text.split(":", 1)
    else:
        rule_method, pattern = "*", rule_text
    rule_method = rule_method.strip().upper() or "*"
    pattern = _normalize_path(pattern)
    if rule_method not in {"*", method}:
        return False
    return fnmatch(path, pattern)


def is_public_request(request: Request, settings: Settings | None = None) -> bool:
    current_settings = settings or get_settings()
    if request.method.upper() == "OPTIONS":
        return True
    return any(_rule_matches(request, rule) for rule in current_settings.auth_public_rules)


def _unauthorized(
    detail: str, *, status_code: int = 401, code: str = "AUTH_REQUIRED", request_id: str = ""
) -> JSONResponse:
    return error_response(status_code, code, detail, request_id=request_id)


def _validate_bearer_token(request: Request, settings: Settings) -> JSONResponse | None:
    header = str(request.headers.get("Authorization") or "").strip()
    if not settings.auth_secret_configured:
        return _unauthorized(
            "Server auth is enabled but FS_AUTH_TOKEN is not configured.",
            status_code=503,
            code="AUTH_NOT_CONFIGURED",
        )
    if not header.lower().startswith("bearer "):
        return _unauthorized("Authentication is required.", code="AUTH_REQUIRED")
    token = header[7:].strip()
    if not token or not secrets.compare_digest(token, settings.auth_token):
        return _unauthorized("Authentication is required.", code="AUTH_INVALID")
    return None


def _validate_api_key(request: Request, settings: Settings) -> JSONResponse | None:
    if not settings.auth_secret_configured:
        return _unauthorized(
            "Server auth is enabled but FS_AUTH_API_KEY is not configured.",
            status_code=503,
            code="AUTH_NOT_CONFIGURED",
        )
    presented = str(request.headers.get(settings.auth_header_name) or "").strip()
    if not presented:
        return _unauthorized("Authentication is required.", code="AUTH_REQUIRED")
    if not secrets.compare_digest(presented, settings.auth_api_key):
        return _unauthorized("Authentication is required.", code="AUTH_INVALID")
    return None


def validate_request_auth(request: Request, settings: Settings | None = None) -> JSONResponse | None:
    current_settings = settings or get_settings()
    if not current_settings.auth_enabled or is_public_request(request, current_settings):
        return None
    if current_settings.effective_auth_mode == "api_key":
        return _validate_api_key(request, current_settings)
    if current_settings.effective_auth_mode == "oidc":
        return None
    return _validate_bearer_token(request, current_settings)


def _origin_from_request(request: Request) -> str:
    origin = str(request.headers.get("Origin") or "").strip().rstrip("/")
    if origin:
        return origin
    referer = str(request.headers.get("Referer") or "").strip()
    if not referer:
        return ""
    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _required_roles(path: str, method: str) -> set[str]:
    lowered = path.casefold()
    if "/admin" in lowered or lowered.startswith("/admin"):
        return {"admin"}
    if "export" in lowered or lowered.endswith("/pdf"):
        return {"admin", "compliance", "exporter"}
    if lowered.startswith("/privacy/v1"):
        return {"admin", "compliance"}
    if lowered.startswith("/crm"):
        return {"admin", "compliance", "crm_manager"}
    if lowered.startswith("/due-diligence"):
        return {"admin", "compliance", "investigator"}
    if lowered.startswith("/data-chat"):
        return {"admin", "analyst", "investigator"}
    if lowered.startswith("/audience-discovery"):
        return {"admin", "analyst"}
    return {"admin", "compliance", "investigator", "analyst", "crm_manager", "viewer"}


def _case_id_from_path(path: str) -> str:
    parts = [part for part in path.split("/") if part]
    try:
        index = parts.index("cases")
    except ValueError:
        return ""
    return parts[index + 1] if len(parts) > index + 1 else ""


def _needs_purpose(path: str) -> bool:
    return path.startswith(
        ("/crm", "/due-diligence", "/data-chat", "/audience-discovery", "/exports")
    ) or "export" in path.casefold()


def _purpose_is_active(purpose_id: str) -> bool:
    try:
        with get_driver().session(database=get_active_database()) as session:
            return bool(
                session.run(
                    """
                    MATCH (purpose:ProcessingPurpose {purposeId: $purposeId, status: 'active'})
                    WHERE purpose.counselDecision = 'approved'
                    RETURN purpose.purposeVersionId AS id LIMIT 1
                    """,
                    {"purposeId": purpose_id},
                ).single()
            )
    except Exception:
        return False


def _authorize_oidc_request(
    request: Request, principal: dict, settings: Settings
) -> JSONResponse | None:
    path = _normalize_path(request.url.path)
    roles = set(principal.get("roles") or [])
    required = _required_roles(path, request.method.upper())
    if not roles.intersection(required):
        return error_response(
            403,
            "ROLE_FORBIDDEN",
            "You do not have permission to perform this action.",
            request_id=str(request.state.request_id),
        )
    case_id = _case_id_from_path(path)
    if case_id and not roles.intersection({"admin", "compliance"}):
        scopes = set(principal.get("caseScopes") or [])
        if "*" not in scopes and case_id not in scopes:
            return error_response(
                403,
                "CASE_FORBIDDEN",
                "You do not have access to this case.",
                request_id=str(request.state.request_id),
            )
    if settings.purpose_enforcement_enabled and _needs_purpose(path):
        purpose_id = str(request.headers.get("X-FS-Purpose-Id") or "").strip()
        if not purpose_id:
            return error_response(
                403,
                "PURPOSE_REQUIRED",
                "An approved processing purpose is required.",
                request_id=str(request.state.request_id),
            )
        scopes = set(principal.get("purposeScopes") or [])
        if "*" not in scopes and purpose_id not in scopes:
            return error_response(
                403,
                "PURPOSE_FORBIDDEN",
                "This processing purpose is not authorized.",
                request_id=str(request.state.request_id),
            )
        if not _purpose_is_active(purpose_id):
            return error_response(
                403,
                "PURPOSE_NOT_ACTIVE",
                "This processing purpose is not active and counsel-approved.",
                request_id=str(request.state.request_id),
            )
        request.state.purpose_id = purpose_id
    return None


def _csrf_failure(request: Request, session: dict, settings: Settings) -> JSONResponse | None:
    if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    origin = _origin_from_request(request)
    if not origin or origin != settings.frontend_origin:
        return error_response(
            403,
            "ORIGIN_FORBIDDEN",
            "The request origin is not permitted.",
            request_id=str(request.state.request_id),
        )
    token = str(request.headers.get(settings.csrf_header_name) or "").strip()
    if not token:
        return error_response(
            403,
            "CSRF_REQUIRED",
            "A CSRF token is required.",
            request_id=str(request.state.request_id),
        )
    expected = str(session.get("csrfHash") or "")
    if not expected or not secrets.compare_digest(
        keyed_hash(settings, "csrf", token), expected
    ):
        return error_response(
            403,
            "CSRF_INVALID",
            "The CSRF token is invalid.",
            request_id=str(request.state.request_id),
        )
    return None


def _audit_event_for_request(request: Request) -> str:
    path = request.url.path.casefold()
    if "export" in path or path.endswith("/pdf"):
        return "export"
    if "search" in path or request.query_params.get("q"):
        return "search"
    return {
        "GET": "view",
        "HEAD": "view",
        "POST": "create",
        "PUT": "update",
        "PATCH": "update",
        "DELETE": "delete",
    }.get(request.method.upper(), "access")


class OptionalAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        request.state.request_id = str(request.headers.get("X-Request-Id") or uuid4())[:80]
        request.state.auth_enabled = settings.auth_enabled
        request.state.auth_mode = settings.effective_auth_mode if settings.auth_enabled else None
        if not settings.auth_enabled or is_public_request(request, settings):
            return await call_next(request)
        if settings.effective_auth_mode != "oidc":
            failure = validate_request_auth(request, settings)
            if failure is not None:
                return failure
            request.state.principal = {
                "principalId": "emergency-shared-gate",
                "email": "",
                "provider": settings.effective_auth_mode,
                "roles": ["admin"],
                "caseScopes": ["*"],
                "purposeScopes": ["*"],
            }
            return await call_next(request)

        raw_session_id = str(request.cookies.get(settings.session_cookie_name) or "")
        session, failure_code = load_auth_session(settings, raw_session_id)
        if session is None:
            status = 403 if failure_code == "ACCESS_REVOKED" else 401
            message = (
                "Access has been revoked."
                if failure_code == "ACCESS_REVOKED"
                else "Authentication is required."
            )
            response = error_response(
                status,
                failure_code or "AUTH_SESSION_INVALID",
                message,
                request_id=str(request.state.request_id),
            )
            response.delete_cookie(
                settings.session_cookie_name,
                path="/",
                secure=settings.session_cookie_secure,
                httponly=True,
                samesite=settings.session_cookie_samesite,
            )
            return response
        principal = {
            "principalId": session.get("allowlistId"),
            "email": session.get("email"),
            "provider": session.get("provider"),
            "issuer": session.get("issuer"),
            "roles": session.get("roles") or [],
            "caseScopes": session.get("caseScopes") or [],
            "purposeScopes": session.get("purposeScopes") or [],
        }
        request.state.principal = principal
        request.state.auth_session = session
        request.state.session_id_hash = session.get("sessionIdHash")

        rate_key = f"protected:{principal['principalId']}:{request.url.path.casefold()}"
        limit = 20 if ("export" in request.url.path.casefold() or "search" in request.url.path.casefold()) else 240
        allowed, retry_after = rate_limiter.allow(rate_key, limit=limit, window_seconds=60)
        if not allowed:
            return error_response(
                429,
                "RATE_LIMITED",
                "Too many requests. Try again later.",
                request_id=str(request.state.request_id),
                retryable=True,
                headers={"Retry-After": str(retry_after)},
            )
        failure = _authorize_oidc_request(request, principal, settings)
        if failure is not None:
            return failure
        failure = _csrf_failure(request, session, settings)
        if failure is not None:
            return failure
        response = await call_next(request)
        try:
            record_auth_audit(
                settings,
                _audit_event_for_request(request),
                outcome="success" if response.status_code < 400 else "denied",
                provider=str(principal.get("provider") or ""),
                issuer=str(principal.get("issuer") or ""),
                subject=str(session.get("subject") or ""),
                allowlist_id=str(principal.get("principalId") or ""),
                request_id=str(request.state.request_id),
                ip_address=str(request.client.host if request.client else ""),
                user_agent=request.headers.get("User-Agent", ""),
                reason_code=f"HTTP_{response.status_code}",
            )
        except Exception:
            # Authentication has already succeeded; never leak audit storage details.
            pass
        response.headers["X-Request-Id"] = str(request.state.request_id)
        return response


class AccessVerifyIn(BaseModel):
    email: str = ""


@router.get("/platform/access/status")
def get_access_status():
    return {"enabled": False, "deprecated": True, "contractVersion": CONTRACT_VERSION}


@router.post("/platform/access/verify")
def verify_access_email(payload: AccessVerifyIn):
    return error_response(
        410,
        "ACCESS_GATE_DEPRECATED",
        "Email verification is not an authentication mechanism. Use organization login.",
    )


@router.get("/platform/auth/status")
def get_auth_status():
    settings = get_settings()
    return {
        "contractVersion": CONTRACT_VERSION,
        "enabled": settings.auth_enabled,
        "mode": settings.effective_auth_mode if settings.auth_enabled else None,
        "configured": settings.auth_secret_configured,
        "header_name": settings.auth_header_name if settings.effective_auth_mode == "api_key" else None,
        "public_rule_count": len(settings.auth_public_rules),
        "organizationLogin": settings.auth_mode == "oidc" and not settings.auth_emergency_bearer_gate,
        "emergencyBearerGate": settings.auth_emergency_bearer_gate,
    }


@router.get("/platform/auth/verify")
def verify_authenticated_access(request: Request):
    """Return success only after middleware has validated the presented credential."""
    settings = get_settings()
    if not settings.auth_enabled:
        return JSONResponse(
            status_code=503,
            content={"detail": "Private platform authentication is disabled."},
        )
    return {
        "authenticated": True,
        "mode": settings.effective_auth_mode,
        "deprecated": settings.effective_auth_mode == "oidc",
    }
