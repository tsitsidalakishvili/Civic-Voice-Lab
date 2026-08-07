import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from .api.router import router as api_router
from .core.auth import OptionalAuthMiddleware
from .core.config import get_settings, validate_auth_startup
from .core.env import load_backend_env
from .core.field_masking import FieldMaskingMiddleware
from .db import (
    close_driver,
    db_health,
    init_approved_processing_purposes,
    init_compliance_backfill,
    init_constraints,
)

logger = logging.getLogger(__name__)
BACKEND_ROOT = Path(__file__).resolve().parents[3]
load_backend_env(BACKEND_ROOT)
settings = get_settings()

app = FastAPI(title=settings.app_title)

# Middleware is added inside-out by Starlette. Authentication must be registered
# first and CORS last so even fail-closed 401/403 responses carry the exact
# allowed-origin headers required by the separate Vercel frontend.
app.add_middleware(OptionalAuthMiddleware)
app.add_middleware(FieldMaskingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Accept",
        "Authorization",
        "Content-Type",
        "X-FS-API-Key",
        "X-FS-CSRF",
        "X-FS-Purpose-Id",
        "Idempotency-Key",
    ],
)

app.include_router(api_router)


@app.get("/")
def root():
    return {
        "service": "fs-deliberation-api",
        "status": "ok",
        "docs": "/docs",
        "health": "/healthz",
        "auth_enabled": settings.auth_enabled,
    }


@app.get("/healthz")
def healthz():
    health = db_health()
    if health.get("ok"):
        return {"status": "ok"}
    return {"status": "degraded"}


@app.get("/health")
def health():
    return healthz()


@app.get("/admin/diagnostics/health")
def detailed_health_diagnostics():
    """Protected operational diagnostics; never add this path to public rules."""
    health = db_health()
    return {
        "status": "ok" if health.get("ok") else "degraded",
        "database": health,
        "startupError": getattr(app.state, "db_bootstrap_error", None),
    }


@app.on_event("startup")
def on_startup():
    validate_auth_startup(settings)
    try:
        init_constraints()
        init_compliance_backfill()
        init_approved_processing_purposes()
        app.state.db_bootstrap_ok = True
    except Exception as exc:
        app.state.db_bootstrap_ok = False
        app.state.db_bootstrap_error = str(exc)
        logger.exception("Deliberation startup: Neo4j initialization failed: %s", exc)
    if settings.auth_enabled and not settings.auth_secret_configured:
        logger.warning("Civic Voice Lab auth is enabled but no auth secret is configured.")


@app.on_event("shutdown")
def on_shutdown():
    close_driver()


@app.exception_handler(ServiceUnavailable)
def handle_neo4j_unavailable(_: Request, exc: ServiceUnavailable):
    logger.exception("Neo4j unavailable: %s", exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Neo4j is unavailable for deliberation backend. "
                "Check DELIBERATION_NEO4J_* / NEO4J_* credentials and network."
            ),
        },
    )


@app.exception_handler(Neo4jError)
def handle_neo4j_error(_: Request, exc: Neo4jError):
    logger.exception("Neo4j query failed: %s", exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Neo4j query failed for deliberation backend. "
                "Verify credentials/database and retry."
            ),
        },
    )


@app.exception_handler(RuntimeError)
def handle_runtime_error(_: Request, exc: RuntimeError):
    message = str(exc)
    if "No working Neo4j configuration" in message:
        logger.exception("Neo4j configuration is invalid or unreachable: %s", exc)
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Neo4j configuration is invalid/unreachable for deliberation backend. "
                    "Set DELIBERATION_NEO4J_* (or NEO4J_*) to a reachable DB."
                ),
            },
        )
    logger.exception("Unhandled runtime error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal service error."})
