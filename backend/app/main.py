import asyncio
import contextlib
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.adapters import get_adapter
from app.api.routes import alerts, auth, cameras, events, system, watchlist
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db import SessionLocal
from app.models import Camera
from app.models.enums import SourceProtocol
from app.services.event_bus import run_subscriber
from app.services.gateway import gateway
from app.services.health_monitor import run_monitor
from app.services.redis_client import close_redis
from app.services.stream_consumer import run_consumer

log = logging.getLogger("netra")

API_DESCRIPTION = """
Unified CCTV monitoring, video-analytics ingestion, watchlist correlation and real-time alerting.

**Authentication**
* Operators / admins: `POST /api/v1/auth/login` → `Authorization: Bearer <jwt>` (or use *Authorize*).
* Machines (AI engines, edge gateways): `X-API-Key: ntr_...` issued via `POST /api/v1/api-clients`.

**Real-time**: `wss://<host>/api/v1/ws?token=<jwt>` streams `detection.created`, `alert.created`,
`alert.updated`, `camera.status` … messages.
"""


async def reconcile_gateway() -> None:
    """Re-register every enabled RTSP/ONVIF camera with the video gateway (idempotent)."""
    await asyncio.sleep(1)
    async with SessionLocal() as db:
        rows = await db.execute(
            select(Camera).where(
                Camera.is_enabled.is_(True),
                Camera.source_protocol.in_([SourceProtocol.RTSP, SourceProtocol.ONVIF]),
            )
        )
        for camera in rows.scalars():
            try:
                await get_adapter(camera.source_protocol).prepare(camera)
            except Exception:
                log.exception("gateway reconcile failed for %s", camera.id)
        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    stop = asyncio.Event()
    tasks = [
        asyncio.create_task(run_subscriber(stop), name="realtime-subscriber"),
        asyncio.create_task(run_consumer(stop), name="stream-consumer"),
        asyncio.create_task(run_monitor(stop), name="health-monitor"),
    ]
    if s.gateway_enabled:
        tasks.append(asyncio.create_task(reconcile_gateway(), name="gateway-reconcile"))
    log.info("Netra API started (env=%s)", s.environment)
    yield
    stop.set()
    for t in tasks:
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t
    await gateway.close()
    await close_redis()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="1.0.0",
        description=API_DESCRIPTION,
        lifespan=lifespan,
        docs_url="/api/docs" if s.api_docs_enabled else None,
        redoc_url="/api/redoc" if s.api_docs_enabled else None,
        openapi_url="/api/openapi.json" if s.api_docs_enabled else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    api = "/api/v1"
    for r in (auth.router, cameras.router, events.router, alerts.router, watchlist.router, system.router):
        app.include_router(r, prefix=api)
    app.include_router(system.ws_router, prefix=api)
    app.include_router(system.health_router, prefix="/api")
    return app


app = create_app()
