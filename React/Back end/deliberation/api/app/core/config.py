import json
import importlib.util
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlparse


DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:5176",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://127.0.0.1:5176",
)

DEFAULT_CORS_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost|127\.0\.0\.1|"
    r"10\.\d+\.\d+\.\d+|"
    r"192\.168\.\d+\.\d+|"
    r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+"
    r")(:\d+)?$"
)

DEFAULT_AUTH_PUBLIC_RULES = (
    "GET:/health",
    "GET:/healthz",
    "GET:/platform/auth/status",
)

DEFAULT_OIDC_PUBLIC_RULES = DEFAULT_AUTH_PUBLIC_RULES + (
    "GET:/auth/login",
    "GET:/auth/callback/google",
    "GET:/auth/callback/entra",
    "POST:/platform/access/verify",
)

DEFAULT_PASSWORD_PUBLIC_RULES = DEFAULT_AUTH_PUBLIC_RULES + (
    "POST:/auth/login",
)

SUPPORTED_AUTH_MODES = {"bearer", "api_key", "oidc", "password"}
GOOGLE_OIDC_ISSUER = "https://accounts.google.com"
DOMAIN_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)

TRUTHY = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return default
    return raw in TRUTHY


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _split_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in str(value).split(",") if item.strip())


def _normalize_config_email(value: object) -> str:
    candidate = str(value or "").strip().lower()
    if candidate.count("@") != 1 or any(char.isspace() or ord(char) < 32 for char in candidate):
        raise ValueError("invalid exact email")
    local, domain = candidate.rsplit("@", 1)
    if not local or len(local) > 64 or local.startswith(".") or local.endswith(".") or ".." in local:
        raise ValueError("invalid exact email")
    try:
        domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("invalid exact email") from exc
    if not DOMAIN_PATTERN.fullmatch(domain):
        raise ValueError("invalid exact email")
    return f"{local}@{domain}"


def _host_is_in_domain(hostname: str | None, domain: str) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    expected = str(domain or "").strip().lower().rstrip(".")
    return bool(host and expected and (host == expected or host.endswith(f".{expected}")))


@dataclass(frozen=True)
class Settings:
    app_title: str
    cors_origins: tuple[str, ...]
    cors_origin_regex: str
    auth_enabled: bool
    auth_mode: str
    auth_token: str
    auth_api_key: str
    auth_header_name: str
    auth_public_rules: tuple[str, ...]
    auth_emergency_bearer_gate: bool
    access_allowed_emails: tuple[str, ...]
    oidc_provider: str
    oidc_issuer: str
    oidc_client_id: str
    oidc_client_secret: str
    oidc_redirect_uri: str
    oidc_google_hosted_domain: str
    oidc_entra_tenant_id: str
    oidc_entra_allow_guests: bool
    oidc_allowed_emails_json: str
    access_users_file: str
    shared_username: str
    shared_password_hash: str
    shared_credential_expires_at: str
    frontend_origin: str
    session_secret: str
    session_cookie_name: str
    session_cookie_secure: bool
    session_cookie_samesite: str
    session_idle_minutes: int
    session_absolute_hours: int
    csrf_header_name: str
    purpose_enforcement_enabled: bool
    field_masking_enabled: bool
    retention_execution_enabled: bool
    compliance_hash_key: str
    direct_marketing_enforcement_enabled: bool
    direct_marketing_purpose_id: str
    election_marketing_rules_enabled: bool
    translation_enabled: bool
    translation_en_ka_model: str
    translation_ka_en_model: str
    translation_worker_url: str
    translation_max_texts: int
    translation_max_chars: int

    @property
    def auth_secret_configured(self) -> bool:
        if self.auth_mode == "password":
            return bool(
                self.access_users_file
                or (self.shared_username and self.shared_password_hash)
            )
        if self.auth_mode == "oidc" and not self.auth_emergency_bearer_gate:
            return self.oidc_configured
        if self.auth_mode == "api_key":
            return bool(self.auth_api_key)
        return bool(self.auth_token)

    @property
    def effective_auth_mode(self) -> str:
        if self.auth_mode == "oidc" and self.auth_emergency_bearer_gate:
            return "bearer"
        return self.auth_mode

    @property
    def oidc_configured(self) -> bool:
        provider_detail = (
            self.oidc_google_hosted_domain
            if self.oidc_provider == "google"
            else self.oidc_entra_tenant_id
        )
        return all(
            (
                self.oidc_provider in {"google", "entra"},
                self.oidc_issuer,
                self.oidc_client_id,
                self.oidc_client_secret,
                self.oidc_redirect_uri,
                provider_detail,
                self.frontend_origin,
                self.session_secret,
                self.oidc_allowed_emails_json,
            )
        )

    @property
    def access_gate_enabled(self) -> bool:
        return bool(self.access_allowed_emails)

    def is_email_allowed(self, email: str) -> bool:
        candidate = str(email or "").strip().lower()
        if not candidate:
            return False
        return candidate in self.access_allowed_emails


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    cors_origins = _split_csv(os.getenv("CORS_ORIGINS")) or DEFAULT_CORS_ORIGINS
    auth_mode = str(os.getenv("FS_AUTH_MODE", "bearer")).strip().lower() or "bearer"
    if auth_mode not in SUPPORTED_AUTH_MODES:
        raise ValueError(
            "FS_AUTH_MODE must be one of bearer, api_key, oidc, or password; invalid modes never fall back."
        )
    frontend_origin = str(os.getenv("FS_FRONTEND_ORIGIN", "")).strip().rstrip("/")
    if auth_mode in {"oidc", "password"} and frontend_origin:
        cors_origins = (frontend_origin,)
    auth_public_rules = (
        _split_csv(os.getenv("FS_AUTH_PUBLIC_RULES"))
        or (
            DEFAULT_OIDC_PUBLIC_RULES
            if auth_mode == "oidc"
            else DEFAULT_PASSWORD_PUBLIC_RULES
            if auth_mode == "password"
            else DEFAULT_AUTH_PUBLIC_RULES
        )
    )
    session_cookie_samesite = str(
        os.getenv("FS_SESSION_COOKIE_SAMESITE", "lax")
    ).strip().lower() or "lax"
    if session_cookie_samesite not in {"lax", "strict", "none"}:
        raise ValueError("FS_SESSION_COOKIE_SAMESITE must be lax, strict, or none.")
    access_users_file = str(os.getenv("FS_ACCESS_USERS_FILE", "")).strip()
    return Settings(
        app_title=str(os.getenv("APP_TITLE", "Civic Voice Lab API")).strip()
        or "Civic Voice Lab API",
        cors_origins=cors_origins,
        cors_origin_regex=str(
            os.getenv("CORS_ORIGIN_REGEX", DEFAULT_CORS_ORIGIN_REGEX)
        ).strip()
        if auth_mode != "oidc"
        else "",
        # Fail closed. Local development may explicitly set FS_AUTH_ENABLED=0.
        auth_enabled=_env_bool("FS_AUTH_ENABLED", default=True),
        auth_mode=auth_mode,
        auth_token=str(os.getenv("FS_AUTH_TOKEN", "")).strip(),
        auth_api_key=str(os.getenv("FS_AUTH_API_KEY", "")).strip(),
        auth_header_name=str(os.getenv("FS_AUTH_HEADER_NAME", "X-FS-API-Key")).strip()
        or "X-FS-API-Key",
        auth_public_rules=auth_public_rules,
        auth_emergency_bearer_gate=_env_bool(
            "FS_AUTH_EMERGENCY_BEARER_GATE_ENABLED", default=False
        ),
        access_allowed_emails=tuple(
            email.lower() for email in _split_csv(os.getenv("FS_ALLOWED_EMAILS"))
        ),
        oidc_provider=str(os.getenv("FS_OIDC_PROVIDER", "")).strip().lower(),
        oidc_issuer=str(os.getenv("FS_OIDC_ISSUER", "")).strip().rstrip("/"),
        oidc_client_id=str(os.getenv("FS_OIDC_CLIENT_ID", "")).strip(),
        oidc_client_secret=str(os.getenv("FS_OIDC_CLIENT_SECRET", "")).strip(),
        oidc_redirect_uri=str(os.getenv("FS_OIDC_REDIRECT_URI", "")).strip(),
        oidc_google_hosted_domain=str(
            os.getenv("FS_OIDC_GOOGLE_HOSTED_DOMAIN", "")
        ).strip().lower(),
        oidc_entra_tenant_id=str(os.getenv("FS_OIDC_ENTRA_TENANT_ID", "")).strip(),
        oidc_entra_allow_guests=_env_bool(
            "FS_OIDC_ENTRA_ALLOW_GUESTS", default=False
        ),
        oidc_allowed_emails_json=str(
            os.getenv("FS_ALLOWED_EMAILS_JSON", "")
        ).strip(),
        access_users_file=access_users_file,
        shared_username=str(os.getenv("FS_SHARED_USERNAME", "")).strip(),
        shared_password_hash=str(os.getenv("FS_SHARED_PASSWORD_HASH", "")).strip(),
        shared_credential_expires_at=str(
            os.getenv("FS_SHARED_CREDENTIAL_EXPIRES_AT", "")
        ).strip(),
        frontend_origin=frontend_origin,
        session_secret=str(os.getenv("FS_SESSION_SECRET", "")).strip(),
        session_cookie_name=str(
            os.getenv("FS_SESSION_COOKIE_NAME", "__Host-fs_session")
        ).strip()
        or "__Host-fs_session",
        session_cookie_secure=_env_bool("FS_SESSION_COOKIE_SECURE", default=True),
        session_cookie_samesite=session_cookie_samesite,
        session_idle_minutes=max(5, _env_int("FS_SESSION_IDLE_MINUTES", 30)),
        session_absolute_hours=max(1, _env_int("FS_SESSION_ABSOLUTE_HOURS", 8)),
        csrf_header_name=str(
            os.getenv("FS_CSRF_HEADER_NAME", "X-FS-CSRF")
        ).strip()
        or "X-FS-CSRF",
        purpose_enforcement_enabled=_env_bool(
            "FS_PURPOSE_ENFORCEMENT_ENABLED", default=True
        ),
        field_masking_enabled=_env_bool("FS_FIELD_MASKING_ENABLED", default=True),
        retention_execution_enabled=_env_bool(
            "FS_RETENTION_EXECUTION_ENABLED", default=False
        ),
        compliance_hash_key=str(
            os.getenv("FS_COMPLIANCE_HASH_KEY", os.getenv("FS_SESSION_SECRET", ""))
        ).strip(),
        direct_marketing_enforcement_enabled=_env_bool(
            "FS_DIRECT_MARKETING_ENFORCEMENT_ENABLED", default=True
        ),
        direct_marketing_purpose_id=str(
            os.getenv("FS_DIRECT_MARKETING_PURPOSE_ID", "direct-marketing")
        ).strip()
        or "direct-marketing",
        election_marketing_rules_enabled=_env_bool(
            "FS_ELECTION_MARKETING_RULES_ENABLED", default=False
        ),
        translation_enabled=_env_bool("FS_TRANSLATION_ENABLED", default=True),
        translation_en_ka_model=str(
            os.getenv(
                "FS_TRANSLATION_EN_KA_MODEL",
                "Helsinki-NLP/opus-mt-synthetic-en-ka",
            )
        ).strip()
        or "Helsinki-NLP/opus-mt-synthetic-en-ka",
        translation_ka_en_model=str(
            os.getenv(
                "FS_TRANSLATION_KA_EN_MODEL",
                "Helsinki-NLP/opus-mt-ka-en",
            )
        ).strip()
        or "Helsinki-NLP/opus-mt-ka-en",
        translation_worker_url=str(
            os.getenv("FS_TRANSLATION_WORKER_URL", "http://127.0.0.1:8011")
        ).strip()
        or "http://127.0.0.1:8011",
        translation_max_texts=max(1, _env_int("FS_TRANSLATION_MAX_TEXTS", 64)),
        translation_max_chars=max(120, _env_int("FS_TRANSLATION_MAX_CHARS", 2200)),
    )


def validate_auth_startup(settings: Settings | None = None) -> None:
    """Reject incomplete or ambiguous authentication configuration at startup."""
    current = settings or get_settings()
    if not current.auth_enabled:
        return
    mode = current.effective_auth_mode
    if mode == "bearer":
        if not current.auth_token:
            raise RuntimeError("FS_AUTH_TOKEN is required when bearer authentication is enabled.")
        return
    if mode == "api_key":
        if not current.auth_api_key:
            raise RuntimeError("FS_AUTH_API_KEY is required when API-key authentication is enabled.")
        return
    if mode == "password":
        if current.access_users_file:
            from .access_users import load_access_users

            try:
                load_access_users(current.access_users_file)
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
            required = {
                "FS_SESSION_SECRET": current.session_secret,
                "FS_FRONTEND_ORIGIN": current.frontend_origin,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise RuntimeError(
                    "Password authentication configuration is incomplete: "
                    + ", ".join(sorted(missing))
                )
        else:
            required = {
                "FS_SHARED_USERNAME": current.shared_username,
                "FS_SHARED_PASSWORD_HASH": current.shared_password_hash,
                "FS_SHARED_CREDENTIAL_EXPIRES_AT": current.shared_credential_expires_at,
                "FS_SESSION_SECRET": current.session_secret,
                "FS_FRONTEND_ORIGIN": current.frontend_origin,
            }
            missing = [name for name, value in required.items() if not value]
            if missing:
                raise RuntimeError(
                    "Password authentication configuration is incomplete: "
                    + ", ".join(sorted(missing))
                )
            if len(current.shared_username) < 8 or len(current.shared_username) > 128:
                raise RuntimeError("FS_SHARED_USERNAME must contain 8 to 128 characters.")
            parts = current.shared_password_hash.split("$")
            if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
                raise RuntimeError("FS_SHARED_PASSWORD_HASH must use the supported PBKDF2 format.")
            try:
                iterations = int(parts[1])
                expires_at = datetime.fromisoformat(
                    current.shared_credential_expires_at.replace("Z", "+00:00")
                )
            except (TypeError, ValueError) as exc:
                raise RuntimeError("Shared credential security parameters are invalid.") from exc
            if iterations < 600_000:
                raise RuntimeError("FS_SHARED_PASSWORD_HASH must use at least 600000 iterations.")
            if expires_at.tzinfo is None:
                raise RuntimeError("FS_SHARED_CREDENTIAL_EXPIRES_AT must include a timezone.")
            if expires_at.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                raise RuntimeError("The shared credential has expired.")
        if len(current.session_secret) < 32:
            raise RuntimeError("FS_SESSION_SECRET must contain at least 32 characters.")
        if current.cors_origins != (current.frontend_origin,):
            raise RuntimeError("Password-mode CORS must contain only the exact FS_FRONTEND_ORIGIN.")
        frontend = urlparse(current.frontend_origin)
        local_frontend = frontend.hostname in {"localhost", "127.0.0.1", "::1"}
        if (
            frontend.scheme not in ({"http", "https"} if local_frontend else {"https"})
            or not frontend.netloc
            or frontend.path not in {"", "/"}
            or frontend.params
            or frontend.query
            or frontend.fragment
            or frontend.username
            or frontend.password
            or "*" in frontend.netloc
        ):
            raise RuntimeError("FS_FRONTEND_ORIGIN must be one exact secure origin.")
        if current.session_cookie_samesite == "none" and not current.session_cookie_secure:
            raise RuntimeError("SameSite=None requires a Secure session cookie.")
        if current.session_cookie_name.startswith("__Host-") and not current.session_cookie_secure:
            raise RuntimeError("__Host- session cookies must be Secure.")
        return
    if current.auth_mode != "oidc":
        raise RuntimeError("Unsupported authentication mode.")
    missing = []
    required = {
        "FS_OIDC_PROVIDER": current.oidc_provider,
        "FS_OIDC_ISSUER": current.oidc_issuer,
        "FS_OIDC_CLIENT_ID": current.oidc_client_id,
        "FS_OIDC_CLIENT_SECRET": current.oidc_client_secret,
        "FS_OIDC_REDIRECT_URI": current.oidc_redirect_uri,
        "FS_ALLOWED_EMAILS_JSON": current.oidc_allowed_emails_json,
        "FS_SESSION_SECRET": current.session_secret,
        "FS_FRONTEND_ORIGIN": current.frontend_origin,
    }
    for name, value in required.items():
        if not value:
            missing.append(name)
    if current.oidc_provider == "google" and not current.oidc_google_hosted_domain:
        missing.append("FS_OIDC_GOOGLE_HOSTED_DOMAIN")
    if current.oidc_provider == "entra" and not current.oidc_entra_tenant_id:
        missing.append("FS_OIDC_ENTRA_TENANT_ID")
    if current.oidc_provider not in {"google", "entra"}:
        raise RuntimeError("FS_OIDC_PROVIDER must explicitly be google or entra.")
    if missing:
        raise RuntimeError("OIDC configuration is incomplete: " + ", ".join(sorted(set(missing))))
    missing_dependencies = [
        package
        for package in ("joserfc", "cryptography")
        if importlib.util.find_spec(package) is None
    ]
    if missing_dependencies:
        raise RuntimeError(
            "OIDC runtime dependencies are missing: " + ", ".join(missing_dependencies)
        )
    if current.oidc_provider == "google" and current.oidc_issuer != GOOGLE_OIDC_ISSUER:
        raise RuntimeError(
            f"Google Workspace OIDC requires FS_OIDC_ISSUER={GOOGLE_OIDC_ISSUER}."
        )
    if current.oidc_provider == "google":
        hosted_domain = current.oidc_google_hosted_domain.rstrip(".")
        if (
            hosted_domain != current.oidc_google_hosted_domain
            or "*" in hosted_domain
            or not DOMAIN_PATTERN.fullmatch(hosted_domain)
        ):
            raise RuntimeError(
                "FS_OIDC_GOOGLE_HOSTED_DOMAIN must be one exact DNS domain without wildcards."
            )
    if len(current.session_secret) < 32:
        raise RuntimeError("FS_SESSION_SECRET must contain at least 32 characters.")
    if "*" in current.cors_origins:
        raise RuntimeError("Wildcard CORS origins are forbidden in OIDC mode.")
    if current.cors_origins != (current.frontend_origin,):
        raise RuntimeError("OIDC CORS must contain only the exact FS_FRONTEND_ORIGIN.")
    frontend = urlparse(current.frontend_origin)
    redirect = urlparse(current.oidc_redirect_uri)
    issuer = urlparse(current.oidc_issuer)
    allowed_schemes = {"https"}
    if frontend.hostname in {"localhost", "127.0.0.1", "::1"}:
        allowed_schemes.add("http")
    if (
        frontend.scheme not in allowed_schemes
        or not frontend.netloc
        or frontend.path not in {"", "/"}
        or frontend.params
        or frontend.query
        or frontend.fragment
        or frontend.username
        or frontend.password
        or "*" in frontend.netloc
    ):
        raise RuntimeError("FS_FRONTEND_ORIGIN must be an exact HTTPS origin (HTTP only for localhost).")
    if (
        redirect.scheme not in allowed_schemes
        or not redirect.netloc
        or redirect.params
        or redirect.query
        or redirect.fragment
        or redirect.username
        or redirect.password
        or "*" in redirect.netloc
    ):
        raise RuntimeError("FS_OIDC_REDIRECT_URI must be HTTPS (HTTP only for localhost development).")
    if (
        issuer.scheme != "https"
        or not issuer.netloc
        or issuer.path not in {"", "/"}
        or issuer.params
        or issuer.query
        or issuer.fragment
        or issuer.username
        or issuer.password
    ):
        raise RuntimeError("FS_OIDC_ISSUER must be an exact HTTPS issuer origin.")
    expected_callback = f"/auth/callback/{current.oidc_provider}"
    if redirect.path.rstrip("/") != expected_callback:
        raise RuntimeError(f"FS_OIDC_REDIRECT_URI path must be exactly {expected_callback}.")
    if current.session_cookie_samesite == "none" and not current.session_cookie_secure:
        raise RuntimeError("SameSite=None requires a Secure session cookie.")
    if current.session_cookie_name.startswith("__Host-") and not current.session_cookie_secure:
        raise RuntimeError("__Host- session cookies must be Secure.")
    if current.oidc_provider == "google":
        same_organization_site = _host_is_in_domain(
            frontend.hostname, current.oidc_google_hosted_domain
        ) and _host_is_in_domain(
            redirect.hostname, current.oidc_google_hosted_domain
        )
        is_local_pair = frontend.hostname in {"localhost", "127.0.0.1", "::1"} and redirect.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if (
            not same_organization_site
            and not is_local_pair
            and current.session_cookie_samesite != "none"
        ):
            raise RuntimeError(
                "Cross-site frontend/API hosting requires FS_SESSION_COOKIE_SAMESITE=none."
            )
    try:
        allowlist = json.loads(current.oidc_allowed_emails_json)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("FS_ALLOWED_EMAILS_JSON must be valid JSON.") from exc
    if not isinstance(allowlist, list) or not allowlist:
        raise RuntimeError("FS_ALLOWED_EMAILS_JSON must be a non-empty JSON array.")
    normalized_allowlist: set[str] = set()
    for entry in allowlist:
        if not isinstance(entry, (str, dict)):
            raise RuntimeError("Every FS_ALLOWED_EMAILS_JSON entry must be an exact email or object.")
        item = {"email": entry} if isinstance(entry, str) else entry
        try:
            normalized_email = _normalize_config_email(item.get("email"))
        except ValueError as exc:
            raise RuntimeError(
                "Every FS_ALLOWED_EMAILS_JSON entry must contain a valid exact email."
            ) from exc
        provider = str(item.get("provider") or current.oidc_provider).strip().lower()
        if provider != current.oidc_provider:
            raise RuntimeError("Allowlist entry provider must match FS_OIDC_PROVIDER.")
        if current.oidc_provider == "google" and normalized_email.rsplit("@", 1)[1] != current.oidc_google_hosted_domain:
            raise RuntimeError(
                "Google allowlist entries must use the exact configured Workspace domain."
            )
        if normalized_email in normalized_allowlist:
            raise RuntimeError("FS_ALLOWED_EMAILS_JSON contains a duplicate exact email.")
        normalized_allowlist.add(normalized_email)
