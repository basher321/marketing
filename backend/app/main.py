"""FastAPI app entry point, middleware, router registration."""
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.config import get_settings
from app.core.logging_config import configure_logging
from app.middleware.body_limit import BodyLimitMiddleware
from app.middleware.error_handler import register_exception_handlers
from app.middleware.rate_limit_middleware import RateLimitMiddleware
from app.middleware.request_id_middleware import RequestIdMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.tenant_middleware import TenantMiddleware
from app.services import scheduler_service
from app.utils.json_response import RoundedJSONResponse

# Not part of the SPEC-BE-002/003 config surface yet — hardcoded here rather
# than added to Settings without a spec update.
API_V1_PREFIX = "/api/v1"

settings = get_settings()

configure_logging()

# SPEC-BE-071 F9: the interactive API docs are off in production.
_PROD = settings.APP_ENV == "production"
app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.APP_DEBUG,
    docs_url=None if _PROD else "/docs",
    redoc_url=None if _PROD else "/redoc",
    openapi_url=None if _PROD else "/openapi.json",
    default_response_class=RoundedJSONResponse,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(RequestIdMiddleware)
# Outermost: an oversized body is refused before anything reads it (SPEC-BE-071 F8).
app.add_middleware(BodyLimitMiddleware)

register_exception_handlers(app)

app.include_router(api_router, prefix=API_V1_PREFIX)


@app.get("/health")
def health_check() -> JSONResponse:
    """Liveness + database reachability (SPEC-BE-071 F13)."""
    from sqlalchemy import text

    from app.db.session import engine

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any failure means the database is unreachable
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unreachable"})
    return JSONResponse(status_code=200, content={"status": "ok", "database": "ok"})


@app.get("/cron/{job_id}", status_code=200)
def run_cron_job(job_id: str, request: Request) -> JSONResponse:
    """Runs one scheduler job on demand, for hosts with no long-running process
    (Vercel Cron calls this with `Authorization: Bearer <CRON_SECRET>`). The job ids
    and functions are the same as the in-process scheduler's (workers/schedules.py);
    keep SCHEDULER_ENABLED=false there, or jobs run twice. 404 while CRON_SECRET is
    empty or for an unknown job, so neither is discoverable."""
    import asyncio
    import hmac

    from app.workers.schedules import JOBS

    secret = settings.CRON_SECRET.get_secret_value()
    given = request.headers.get("authorization", "")
    job = next((j for j in JOBS if j["id"] == job_id), None)
    if not secret or job is None:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    if not hmac.compare_digest(given.encode(), f"Bearer {secret}".encode()):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    result = job["func"]()
    if asyncio.iscoroutine(result):
        result = asyncio.run(result)
    return JSONResponse(status_code=200, content={"job": job_id, "result": jsonable_encoder(result)})


def _refuse_superuser_database() -> None:
    """SPEC-BE-071 F4: in production the app must not connect as a database
    superuser or a role that bypasses row-level security."""
    from sqlalchemy import text

    from app.db.session import engine

    with engine.connect() as conn:
        superuser, bypass = conn.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
    if superuser or bypass:
        raise RuntimeError("Refusing to start in production: the database login is a superuser or bypasses RLS. "
                           "Use a least-privilege role (see SPEC-BE-071 operator checklist).")


@app.on_event("startup")
def on_startup() -> None:
    if get_settings().APP_ENV == "production":
        _refuse_superuser_database()
    if get_settings().META_FAKE_TRANSPORT:
        # Dev-only fixtures for Meta/Shopify/WooCommerce (refused in production by config).
        from app.integrations import dev_fakes

        dev_fakes.install()
    scheduler_service.start_scheduler()


@app.on_event("shutdown")
def on_shutdown() -> None:
    scheduler_service.shutdown_scheduler()
