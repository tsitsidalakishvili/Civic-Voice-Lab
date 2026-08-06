import os
from dataclasses import dataclass
from functools import lru_cache


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
    r"172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|"
    r"[a-z0-9-]+\.vercel\.app|"
    r"[a-z0-9-]+\.netlify\.app"
    r")(:\d+)?$"
)

DEFAULT_AUTH_PUBLIC_RULES = (
    "*:/",
    "*:/health",
    "*:/healthz",
    "*:/docs",
    "*:/docs/*",
    "*:/openapi.json",
    "*:/redoc",
    "*:/platform/auth/status",
    "GET:/platform/access/status",
    "POST:/platform/access/verify",
    "POST:/platform/translate",
    "GET:/reports/public/*",
    "GET:/crm/events/detail",
    "POST:/crm/events/*/register",
    "POST:/crm/events/*/register/bulk",
    "GET:/crm/campaigns",
    "GET:/crm/campaigns/*",
    "POST:/crm/campaigns/*/contributions/checkout",
    "POST:/crm/campaigns/*/volunteers",
    "POST:/crm/payments/webhook",
    "POST:/crm/supporter-signup",
    "GET:/crm/supporter-signup-config",
    "GET:/conversations/*",
    "POST:/conversations/*/queue",
    "POST:/conversations/*/view",
    "GET:/conversations/*/invite/validate",
    "GET:/conversations/*/comments",
    "POST:/conversations/*/comments",
    "POST:/vote",
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
    access_allowed_emails: tuple[str, ...]
    translation_enabled: bool
    translation_en_ka_model: str
    translation_ka_en_model: str
    translation_worker_url: str
    translation_max_texts: int
    translation_max_chars: int

    @property
    def auth_secret_configured(self) -> bool:
        if self.auth_mode == "api_key":
            return bool(self.auth_api_key)
        return bool(self.auth_token)

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
    if auth_mode not in {"bearer", "api_key"}:
        auth_mode = "bearer"
    auth_public_rules = (
        _split_csv(os.getenv("FS_AUTH_PUBLIC_RULES")) or DEFAULT_AUTH_PUBLIC_RULES
    )
    return Settings(
        app_title=str(os.getenv("APP_TITLE", "Civic Voice Lab API")).strip()
        or "Civic Voice Lab API",
        cors_origins=cors_origins,
        cors_origin_regex=str(
            os.getenv("CORS_ORIGIN_REGEX", DEFAULT_CORS_ORIGIN_REGEX)
        ).strip()
        or DEFAULT_CORS_ORIGIN_REGEX,
        auth_enabled=_env_bool("FS_AUTH_ENABLED", default=False),
        auth_mode=auth_mode,
        auth_token=str(os.getenv("FS_AUTH_TOKEN", "")).strip(),
        auth_api_key=str(os.getenv("FS_AUTH_API_KEY", "")).strip(),
        auth_header_name=str(os.getenv("FS_AUTH_HEADER_NAME", "X-FS-API-Key")).strip()
        or "X-FS-API-Key",
        auth_public_rules=auth_public_rules,
        access_allowed_emails=tuple(
            email.lower() for email in _split_csv(os.getenv("FS_ALLOWED_EMAILS"))
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
