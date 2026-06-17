import os
import logging

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from neo4j.exceptions import Neo4jError, ServiceUnavailable

load_dotenv(
    dotenv_path=os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
    ),
    override=True,
)

from .db import close_driver, db_health, init_constraints
from .routes import router

logger = logging.getLogger(__name__)

app = FastAPI(title="Polis-style Deliberation API")
app.include_router(router)


@app.get("/")
def root():
    return {
        "service": "fs-deliberation-api",
        "status": "ok",
        "docs": "/docs",
        "health": "/healthz",
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
