import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from .api.router import router as api_router
from .core.auth import OptionalAuthMiddleware
from .core.config import get_settings
from .core.env import load_backend_env
from .db import close_driver, db_health, init_constraints

logger = logging.getLogger(__name__)
BACKEND_ROOT = Path(__file__).resolve().parents[3]
load_backend_env(BACKEND_ROOT)
settings = get_settings()

app = FastAPI(title=settings.app_title)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(OptionalAuthMiddleware)

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
        return {
            "status": "ok",
            "db": "ok",
            "target_source": health.get("target_source"),
            "target_uri": health.get("target_uri"),
            "target_database": health.get("target_database"),
        }
    return {
        "status": "degraded",
        "db": "error",
        "detail": health.get("error"),
        "startup_error": getattr(app.state, "db_bootstrap_error", None),
    }


@app.get("/health")
def health():
    return healthz()


@app.on_event("startup")
def on_startup():
    try:
        init_constraints()
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
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Neo4j is unavailable for deliberation backend. "
                "Check DELIBERATION_NEO4J_* / NEO4J_* credentials and network."
            ),
            "error": str(exc),
        },
    )


@app.exception_handler(Neo4jError)
def handle_neo4j_error(_: Request, exc: Neo4jError):
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Neo4j query failed for deliberation backend. "
                "Verify credentials/database and retry."
            ),
            "error": str(exc),
        },
    )


@app.exception_handler(RuntimeError)
def handle_runtime_error(_: Request, exc: RuntimeError):
    message = str(exc)
    if "No working Neo4j configuration" in message:
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "Neo4j configuration is invalid/unreachable for deliberation backend. "
                    "Set DELIBERATION_NEO4J_* (or NEO4J_*) to a reachable DB."
                ),
                "error": message,
            },
        )
    return JSONResponse(status_code=500, content={"detail": message})
