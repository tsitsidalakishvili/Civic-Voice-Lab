import secrets
from fnmatch import fnmatch

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings, get_settings

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


def _unauthorized(detail: str, *, status_code: int = 401) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


def _validate_bearer_token(request: Request, settings: Settings) -> JSONResponse | None:
    header = str(request.headers.get("Authorization") or "").strip()
    if not settings.auth_secret_configured:
        return _unauthorized(
            "Server auth is enabled but FS_AUTH_TOKEN is not configured.",
            status_code=503,
        )
    if not header.lower().startswith("bearer "):
        return _unauthorized("Missing bearer token.")
    token = header[7:].strip()
    if not token or not secrets.compare_digest(token, settings.auth_token):
        return _unauthorized("Invalid bearer token.")
    return None


def _validate_api_key(request: Request, settings: Settings) -> JSONResponse | None:
    if not settings.auth_secret_configured:
        return _unauthorized(
            "Server auth is enabled but FS_AUTH_API_KEY is not configured.",
            status_code=503,
        )
    presented = str(request.headers.get(settings.auth_header_name) or "").strip()
    if not presented:
        return _unauthorized(f"Missing {settings.auth_header_name} header.")
    if not secrets.compare_digest(presented, settings.auth_api_key):
        return _unauthorized("Invalid API key.")
    return None


def validate_request_auth(request: Request, settings: Settings | None = None) -> JSONResponse | None:
    current_settings = settings or get_settings()
    if not current_settings.auth_enabled or is_public_request(request, current_settings):
        return None
    if current_settings.auth_mode == "api_key":
        return _validate_api_key(request, current_settings)
    return _validate_bearer_token(request, current_settings)


class OptionalAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        failure = validate_request_auth(request, settings)
        if failure is not None:
            return failure
        request.state.auth_enabled = settings.auth_enabled
        request.state.auth_mode = settings.auth_mode if settings.auth_enabled else None
        return await call_next(request)


class AccessVerifyIn(BaseModel):
    email: str = ""


@router.get("/platform/access/status")
def get_access_status():
    settings = get_settings()
    return {"enabled": settings.access_gate_enabled}


@router.post("/platform/access/verify")
def verify_access_email(payload: AccessVerifyIn):
    settings = get_settings()
    if not settings.access_gate_enabled:
        return {"allowed": True, "enabled": False}
    email = str(payload.email or "").strip().lower()
    return {"allowed": settings.is_email_allowed(email), "enabled": True}


@router.get("/platform/auth/status")
def get_auth_status():
    settings = get_settings()
    return {
        "enabled": settings.auth_enabled,
        "mode": settings.auth_mode if settings.auth_enabled else None,
        "configured": settings.auth_secret_configured,
        "header_name": settings.auth_header_name if settings.auth_mode == "api_key" else None,
        "public_rule_count": len(settings.auth_public_rules),
    }
