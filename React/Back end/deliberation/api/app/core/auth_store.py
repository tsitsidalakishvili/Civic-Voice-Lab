from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from ..db import get_active_database, get_driver
from .config import Settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None = None) -> str:
    return (value or utc_now()).astimezone(timezone.utc).isoformat()


def normalize_exact_email(value: str) -> str:
    candidate = str(value or "").strip().lower()
    if (
        not candidate
        or len(candidate) > 320
        or candidate.count("@") != 1
        or any(char.isspace() or ord(char) < 32 for char in candidate)
    ):
        raise ValueError("A valid email address is required.")
    local, domain = candidate.rsplit("@", 1)
    if (
        not local
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or not domain
    ):
        raise ValueError("A valid email address is required.")
    try:
        canonical_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("A valid email domain is required.") from exc
    labels = canonical_domain.split(".")
    if (
        len(canonical_domain) > 253
        or len(labels) < 2
        or any(
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not all(char.isalnum() or char == "-" for char in label)
            for label in labels
        )
    ):
        raise ValueError("A valid email domain is required.")
    # Deliberately do not rewrite dots or plus aliases in the local part.
    return f"{local}@{canonical_domain}"


def keyed_hash(settings: Settings, purpose: str, value: str) -> str:
    secret = settings.compliance_hash_key or settings.session_secret
    if not secret:
        raise RuntimeError("A server-side compliance/session hashing key is required.")
    return hmac.new(
        secret.encode("utf-8"),
        f"{purpose}:{value}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def encrypt_short_secret(settings: Settings, value: str) -> str:
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - startup validation covers deployment
        raise RuntimeError("cryptography is required for OIDC secret storage.") from exc
    digest = hashlib.sha256(settings.session_secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key).encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_short_secret(settings: Settings, value: str) -> str:
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(settings.session_secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key).decrypt(value.encode("ascii")).decode("utf-8")


def _read(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    driver = get_driver()
    with driver.session(database=get_active_database()) as session:
        result = session.run(query, params or {})
        return [record.data() for record in result]


def _write(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    driver = get_driver()
    with driver.session(database=get_active_database()) as session:
        if hasattr(session, "execute_write"):
            return session.execute_write(
                lambda tx: [record.data() for record in tx.run(query, params or {})]
            )
        return session.write_transaction(  # pragma: no cover - legacy driver
            lambda tx: [record.data() for record in tx.run(query, params or {})]
        )


def record_auth_audit(
    settings: Settings,
    event_type: str,
    *,
    outcome: str,
    provider: str = "",
    issuer: str = "",
    subject: str = "",
    allowlist_id: str = "",
    request_id: str = "",
    ip_address: str = "",
    user_agent: str = "",
    reason_code: str = "",
) -> None:
    params = {
        "eventId": str(uuid4()),
        "eventType": str(event_type)[:80],
        "outcome": str(outcome)[:30],
        "provider": str(provider)[:30],
        "issuer": str(issuer)[:300],
        "subjectHash": keyed_hash(settings, "oidc-subject", subject) if subject else "",
        "allowlistId": str(allowlist_id)[:80],
        "requestId": str(request_id)[:80],
        "ipHash": keyed_hash(settings, "request-ip", ip_address) if ip_address else "",
        "userAgentHash": keyed_hash(settings, "user-agent", user_agent) if user_agent else "",
        "reasonCode": str(reason_code)[:80],
    }
    _write(
        """
        CREATE (event:AuthAuditEvent {
          eventId: $eventId, eventType: $eventType, outcome: $outcome,
          provider: $provider, issuer: $issuer, subjectHash: $subjectHash,
          allowlistId: $allowlistId, requestId: $requestId,
          ipHash: $ipHash, userAgentHash: $userAgentHash,
          reasonCode: $reasonCode, createdAt: datetime()
        })
        """,
        params,
    )


def create_oidc_transaction(
    settings: Settings,
    *,
    provider: str,
    state: str,
    nonce: str,
    pkce_verifier: str,
    redirect_uri: str,
    return_to: str,
    ttl_minutes: int = 10,
) -> str:
    transaction_id = str(uuid4())
    expires_at = utc_now() + timedelta(minutes=ttl_minutes)
    _write(
        """
        CREATE (tx:OidcLoginTransaction {
          transactionId: $transactionId, stateHash: $stateHash,
          provider: $provider, nonceHash: $nonceHash,
          pkceVerifierCiphertext: $pkceVerifierCiphertext,
          redirectUri: $redirectUri, returnTo: $returnTo,
          createdAt: datetime(), expiresAt: datetime($expiresAt), usedAt: null
        })
        """,
        {
            "transactionId": transaction_id,
            "stateHash": keyed_hash(settings, "oidc-state", state),
            "provider": provider,
            "nonceHash": keyed_hash(settings, "oidc-nonce", nonce),
            "pkceVerifierCiphertext": encrypt_short_secret(settings, pkce_verifier),
            "redirectUri": redirect_uri,
            "returnTo": return_to,
            "expiresAt": iso(expires_at),
        },
    )
    return transaction_id


def consume_oidc_transaction(settings: Settings, state: str, provider: str) -> dict[str, Any] | None:
    rows = _write(
        """
        MATCH (tx:OidcLoginTransaction {stateHash: $stateHash, provider: $provider})
        WHERE tx.usedAt IS NULL AND tx.expiresAt > datetime()
        SET tx.usedAt = datetime()
        RETURN tx.transactionId AS transactionId,
               tx.nonceHash AS nonceHash,
               tx.pkceVerifierCiphertext AS pkceVerifierCiphertext,
               tx.redirectUri AS redirectUri,
               tx.returnTo AS returnTo
        """,
        {
            "stateHash": keyed_hash(settings, "oidc-state", state),
            "provider": provider,
        },
    )
    if not rows:
        return None
    row = rows[0]
    row["pkceVerifier"] = decrypt_short_secret(
        settings, str(row.pop("pkceVerifierCiphertext") or "")
    )
    return row


def _parse_allowlist(settings: Settings) -> list[dict[str, Any]]:
    try:
        raw = json.loads(settings.oidc_allowed_emails_json or "[]")
    except (TypeError, ValueError):
        return []
    parsed: list[dict[str, Any]] = []
    for entry in raw if isinstance(raw, list) else []:
        item = {"email": entry} if isinstance(entry, str) else dict(entry or {})
        try:
            email = normalize_exact_email(str(item.get("email") or ""))
        except ValueError:
            continue
        provider = str(item.get("provider") or settings.oidc_provider).strip().lower()
        if provider != settings.oidc_provider:
            continue
        parsed.append(
            {
                "email": email,
                "provider": provider,
                "roles": [str(role).strip() for role in item.get("roles", ["viewer"]) if str(role).strip()],
                "caseScopes": [str(case).strip() for case in item.get("caseScopes", []) if str(case).strip()],
                "purposeScopes": [str(purpose).strip() for purpose in item.get("purposeScopes", []) if str(purpose).strip()],
                "validFrom": item.get("validFrom"),
                "validUntil": item.get("validUntil"),
                "reason": str(item.get("reason") or "initial-server-allowlist")[:200],
            }
        )
    return parsed


def authorize_and_bind_allowlist(
    settings: Settings,
    *,
    email: str,
    provider: str,
    issuer: str,
    subject: str,
) -> dict[str, Any] | None:
    if (
        provider != settings.oidc_provider
        or str(issuer or "").rstrip("/") != settings.oidc_issuer.rstrip("/")
        or not str(subject or "").strip()
    ):
        return None
    normalized = normalize_exact_email(email)
    configured = next(
        (
            item
            for item in _parse_allowlist(settings)
            if item["email"] == normalized and item["provider"] == provider
        ),
        None,
    )
    if configured is None:
        return None
    email_hash = keyed_hash(settings, "allowlist-email", normalized)
    entry_key = keyed_hash(settings, "allowlist-entry", f"{provider}:{normalized}")
    rows = _write(
        """
        MERGE (entry:AuthAllowlistEntry {entryKey: $entryKey})
        ON CREATE SET entry.allowlistId = $allowlistId,
                      entry.emailHash = $emailHash,
                      entry.provider = $provider,
                      entry.normalizedEmail = $normalizedEmail,
                      entry.createdAt = datetime(), entry.addedAt = datetime(),
                      entry.addedBy = 'server-config', entry.version = 1,
                      entry.status = 'active'
        WITH entry
        WHERE coalesce(entry.status, 'active') = 'active'
          AND (entry.validFrom IS NULL OR entry.validFrom <= datetime())
          AND (entry.validUntil IS NULL OR entry.validUntil > datetime())
          AND (entry.issuer IS NULL OR entry.issuer = '' OR entry.issuer = $issuer)
          AND (entry.subject IS NULL OR entry.subject = '' OR entry.subject = $subject)
        SET entry.issuer = CASE WHEN entry.issuer IS NULL OR entry.issuer = '' THEN $issuer ELSE entry.issuer END,
            entry.subject = CASE WHEN entry.subject IS NULL OR entry.subject = '' THEN $subject ELSE entry.subject END,
            entry.roles = $roles, entry.caseScopes = $caseScopes,
            entry.purposeScopes = $purposeScopes,
            entry.validFrom = CASE WHEN $validFrom IS NULL THEN entry.validFrom ELSE datetime($validFrom) END,
            entry.validUntil = CASE WHEN $validUntil IS NULL THEN entry.validUntil ELSE datetime($validUntil) END,
            entry.reason = $reason, entry.updatedAt = datetime()
        RETURN entry.allowlistId AS allowlistId,
               entry.normalizedEmail AS email, entry.provider AS provider,
               entry.issuer AS issuer, entry.subject AS subject,
               coalesce(entry.roles, []) AS roles,
               coalesce(entry.caseScopes, []) AS caseScopes,
               coalesce(entry.purposeScopes, []) AS purposeScopes,
               coalesce(entry.version, 1) AS version
        """,
        {
            "emailHash": email_hash,
            "entryKey": entry_key,
            "allowlistId": str(uuid4()),
            "normalizedEmail": normalized,
            "provider": provider,
            "issuer": issuer,
            "subject": subject,
            "roles": configured["roles"] or ["viewer"],
            "caseScopes": configured["caseScopes"],
            "purposeScopes": configured["purposeScopes"],
            "validFrom": configured.get("validFrom"),
            "validUntil": configured.get("validUntil"),
            "reason": configured["reason"],
        },
    )
    return rows[0] if rows else None


def authorize_shared_credential(settings: Settings) -> dict[str, Any] | None:
    """Create or refresh the single temporary shared principal without storing credentials."""
    username_hash = keyed_hash(settings, "shared-username", settings.shared_username)
    entry_key = keyed_hash(settings, "allowlist-entry", f"password:{username_hash}")
    rows = _write(
        """
        MERGE (entry:AuthAllowlistEntry {entryKey: $entryKey})
        ON CREATE SET entry.allowlistId = $allowlistId,
                      entry.emailHash = '', entry.normalizedEmail = '',
                      entry.provider = 'password', entry.issuer = 'fs:shared-credential',
                      entry.subject = $subject, entry.createdAt = datetime(),
                      entry.addedAt = datetime(), entry.addedBy = 'server-config',
                      entry.version = 1, entry.status = 'active'
        SET entry.roles = ['admin'], entry.caseScopes = ['*'],
            entry.purposeScopes = ['*'], entry.validUntil = datetime($validUntil),
            entry.reason = 'temporary-shared-credential', entry.updatedAt = datetime()
        RETURN entry.allowlistId AS allowlistId, '' AS email,
               entry.provider AS provider, entry.issuer AS issuer,
               entry.subject AS subject, entry.roles AS roles,
               entry.caseScopes AS caseScopes, entry.purposeScopes AS purposeScopes,
               entry.version AS version
        """,
        {
            "entryKey": entry_key,
            "allowlistId": str(uuid4()),
            "subject": username_hash,
            "validUntil": settings.shared_credential_expires_at,
        },
    )
    return rows[0] if rows else None


def authorize_password_user(settings: Settings, email: str) -> dict[str, Any] | None:
    """Create or refresh one file-authorized user; every listed user has equal access."""
    normalized = normalize_exact_email(email)
    email_hash = keyed_hash(settings, "allowlist-email", normalized)
    entry_key = keyed_hash(settings, "allowlist-entry", f"password:{email_hash}")
    rows = _write(
        """
        MERGE (entry:AuthAllowlistEntry {entryKey: $entryKey})
        ON CREATE SET entry.allowlistId = $allowlistId,
                      entry.emailHash = $emailHash,
                      entry.normalizedEmail = $normalizedEmail,
                      entry.provider = 'password', entry.issuer = 'fs:access-users-file',
                      entry.subject = $subject, entry.createdAt = datetime(),
                      entry.addedAt = datetime(), entry.addedBy = 'server-config',
                      entry.version = 1, entry.status = 'active'
        SET entry.roles = ['admin'], entry.caseScopes = ['*'],
            entry.purposeScopes = ['*'], entry.reason = 'file-access-user',
            entry.status = 'active', entry.updatedAt = datetime()
        RETURN entry.allowlistId AS allowlistId, entry.normalizedEmail AS email,
               entry.provider AS provider, entry.issuer AS issuer,
               entry.subject AS subject, entry.roles AS roles,
               entry.caseScopes AS caseScopes, entry.purposeScopes AS purposeScopes,
               entry.version AS version
        """,
        {
            "entryKey": entry_key,
            "allowlistId": str(uuid4()),
            "emailHash": email_hash,
            "normalizedEmail": normalized,
            "subject": email_hash,
        },
    )
    return rows[0] if rows else None


def create_auth_session(
    settings: Settings, principal: dict[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    raw_session_id = secrets.token_urlsafe(48)
    raw_csrf_token = secrets.token_urlsafe(36)
    now = utc_now()
    idle_expires = now + timedelta(minutes=settings.session_idle_minutes)
    absolute_expires = now + timedelta(hours=settings.session_absolute_hours)
    session_hash = keyed_hash(settings, "auth-session", raw_session_id)
    _write(
        """
        MATCH (entry:AuthAllowlistEntry {allowlistId: $allowlistId})
        CREATE (session:AuthSession {
          sessionIdHash: $sessionIdHash, allowlistId: $allowlistId,
          provider: $provider, issuer: $issuer, subjectHash: $subjectHash,
          roles: $roles, caseScopes: $caseScopes, purposeScopes: $purposeScopes,
          issuedAt: datetime($issuedAt), lastSeenAt: datetime($issuedAt),
          idleExpiresAt: datetime($idleExpiresAt),
          absoluteExpiresAt: datetime($absoluteExpiresAt), revokedAt: null,
          sessionVersion: $sessionVersion, csrfHash: $csrfHash,
          csrfCiphertext: $csrfCiphertext
        })
        MERGE (entry)-[:HAS_AUTH_SESSION]->(session)
        """,
        {
            "sessionIdHash": session_hash,
            "allowlistId": principal["allowlistId"],
            "provider": principal["provider"],
            "issuer": principal["issuer"],
            "subjectHash": keyed_hash(settings, "oidc-subject", principal["subject"]),
            "roles": principal.get("roles") or [],
            "caseScopes": principal.get("caseScopes") or [],
            "purposeScopes": principal.get("purposeScopes") or [],
            "issuedAt": iso(now),
            "idleExpiresAt": iso(idle_expires),
            "absoluteExpiresAt": iso(absolute_expires),
            "sessionVersion": int(principal.get("version") or 1),
            "csrfHash": keyed_hash(settings, "csrf", raw_csrf_token),
            "csrfCiphertext": encrypt_short_secret(settings, raw_csrf_token),
        },
    )
    session = {
        "sessionIdHash": session_hash,
        "issuedAt": iso(now),
        "lastSeenAt": iso(now),
        "idleExpiresAt": iso(idle_expires),
        "absoluteExpiresAt": iso(absolute_expires),
    }
    return raw_session_id, raw_csrf_token, session


def load_auth_session(settings: Settings, raw_session_id: str) -> tuple[dict[str, Any] | None, str]:
    if not raw_session_id:
        return None, "AUTH_SESSION_MISSING"
    session_hash = keyed_hash(settings, "auth-session", raw_session_id)
    rows = _read(
        """
        MATCH (session:AuthSession {sessionIdHash: $sessionIdHash})
        OPTIONAL MATCH (entry:AuthAllowlistEntry {allowlistId: session.allowlistId})
        RETURN session.sessionIdHash AS sessionIdHash,
               toString(session.issuedAt) AS issuedAt,
               toString(session.lastSeenAt) AS lastSeenAt,
               toString(session.idleExpiresAt) AS idleExpiresAt,
               toString(session.absoluteExpiresAt) AS absoluteExpiresAt,
               toString(session.revokedAt) AS revokedAt,
               session.sessionVersion AS sessionVersion,
               session.csrfHash AS csrfHash,
               session.csrfCiphertext AS csrfCiphertext,
               entry.allowlistId AS allowlistId,
               entry.normalizedEmail AS email, entry.provider AS provider,
               entry.issuer AS issuer, entry.subject AS subject,
               coalesce(entry.roles, []) AS roles,
               coalesce(entry.caseScopes, []) AS caseScopes,
               coalesce(entry.purposeScopes, []) AS purposeScopes,
               coalesce(entry.version, 1) AS allowlistVersion,
               coalesce(entry.status, 'revoked') AS allowlistStatus,
               toString(entry.validFrom) AS validFrom,
               toString(entry.validUntil) AS validUntil
        """,
        {"sessionIdHash": session_hash},
    )
    if not rows:
        return None, "AUTH_SESSION_INVALID"
    row = rows[0]
    now = utc_now()

    def parse_dt(value: Any) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    if row.get("revokedAt"):
        return None, "AUTH_SESSION_REVOKED"
    if (parse_dt(row.get("idleExpiresAt")) or now) <= now or (
        parse_dt(row.get("absoluteExpiresAt")) or now
    ) <= now:
        return None, "AUTH_SESSION_EXPIRED"
    if row.get("allowlistStatus") != "active" or not row.get("allowlistId"):
        return None, "ACCESS_REVOKED"
    if int(row.get("sessionVersion") or 0) != int(row.get("allowlistVersion") or 0):
        return None, "AUTH_SESSION_REVOKED"
    valid_from = parse_dt(row.get("validFrom"))
    valid_until = parse_dt(row.get("validUntil"))
    if (valid_from and valid_from > now) or (valid_until and valid_until <= now):
        return None, "ACCESS_REVOKED"
    new_idle = min(
        now + timedelta(minutes=settings.session_idle_minutes),
        parse_dt(row.get("absoluteExpiresAt")) or now,
    )
    _write(
        """
        MATCH (session:AuthSession {sessionIdHash: $sessionIdHash})
        SET session.lastSeenAt = datetime($lastSeenAt),
            session.idleExpiresAt = datetime($idleExpiresAt)
        """,
        {
            "sessionIdHash": session_hash,
            "lastSeenAt": iso(now),
            "idleExpiresAt": iso(new_idle),
        },
    )
    row["lastSeenAt"] = iso(now)
    row["idleExpiresAt"] = iso(new_idle)
    row["csrfToken"] = decrypt_short_secret(settings, str(row.pop("csrfCiphertext") or ""))
    return row, ""


def revoke_auth_session(session_hash: str) -> bool:
    rows = _write(
        """
        MATCH (session:AuthSession {sessionIdHash: $sessionIdHash})
        WHERE session.revokedAt IS NULL
        SET session.revokedAt = datetime()
        RETURN session.sessionIdHash AS sessionIdHash
        """,
        {"sessionIdHash": session_hash},
    )
    return bool(rows)
