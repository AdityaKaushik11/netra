import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, admin_only, any_user
from app.core.config import get_settings
from app.core.security import decode_token
from app.db import SessionLocal
from app.models import Alert, AuditLog, Camera, DetectionEvent, User, WatchlistEntry
from app.models.enums import AlertStatus, CameraStatus, Severity
from app.services import sessions
from app.services.event_bus import manager
from app.services.gateway import gateway
from app.services.redis_client import get_redis
from app.services.watchlist_matcher import matcher

router = APIRouter()
OPEN = [AlertStatus.NEW, AlertStatus.ACKNOWLEDGED]


@router.get("/stats/overview", tags=["stats"])
async def overview(db: AsyncSession = DB, _: User = Depends(any_user)):
    """Single call that powers the dashboard KPI strip."""
    now = datetime.now(UTC)
    cam_rows = dict(
        (
            await db.execute(
                select(Camera.status, func.count()).where(Camera.is_enabled.is_(True)).group_by(Camera.status)
            )
        ).all()
    )
    disabled = await db.scalar(select(func.count()).select_from(Camera).where(Camera.is_enabled.is_(False)))
    sev_rows = dict(
        (
            await db.execute(
                select(Alert.severity, func.count()).where(Alert.status.in_(OPEN)).group_by(Alert.severity)
            )
        ).all()
    )
    new_alerts = await db.scalar(select(func.count()).select_from(Alert).where(Alert.status == AlertStatus.NEW))

    async def events_since(delta: timedelta) -> int:
        return (
            await db.scalar(
                select(func.count()).select_from(DetectionEvent).where(DetectionEvent.received_at >= now - delta)
            )
            or 0
        )

    reads_24h = await db.scalar(
        select(func.coalesce(func.sum(DetectionEvent.repeat_count), 0)).where(
            DetectionEvent.received_at >= now - timedelta(hours=24)
        )
    )
    alerts_24h = await db.scalar(
        select(func.count()).select_from(Alert).where(Alert.triggered_at >= now - timedelta(hours=24))
    )
    watch_active = await db.scalar(
        select(func.count()).select_from(WatchlistEntry).where(WatchlistEntry.is_active.is_(True))
    )
    top = await db.execute(
        select(DetectionEvent.camera_id, func.count())
        .where(DetectionEvent.received_at >= now - timedelta(hours=24))
        .group_by(DetectionEvent.camera_id)
        .order_by(func.count().desc())
        .limit(5)
    )
    events_5m = await events_since(timedelta(minutes=5))
    return {
        "system": await _service_health(),
        "cameras": {
            "online": cam_rows.get(CameraStatus.ONLINE, 0),
            "degraded": cam_rows.get(CameraStatus.DEGRADED, 0),
            "offline": cam_rows.get(CameraStatus.OFFLINE, 0),
            "unknown": cam_rows.get(CameraStatus.UNKNOWN, 0),
            "disabled": disabled or 0,
            "total": sum(cam_rows.values()) + (disabled or 0),
        },
        "alerts": {
            "open": sum(sev_rows.values()),
            "new": new_alerts or 0,
            "by_severity": {s.value: sev_rows.get(s, 0) for s in Severity},
            "last_24h": alerts_24h or 0,
        },
        "events": {
            "last_5m": events_5m,
            "last_hour": await events_since(timedelta(hours=1)),
            "last_24h": await events_since(timedelta(hours=24)),
            "per_minute": round(events_5m / 5, 1),
            "duplicates_suppressed_24h": int(reads_24h or 0),
        },
        "watchlist": {"active": watch_active or 0, "cached": matcher.size},
        "top_cameras_24h": [{"camera_id": c, "events": n} for c, n in top.all()],
        "realtime": {"ws_clients_this_node": manager.count},
        "server_time": now,
    }


_health_cache: tuple[float, dict] = (0.0, {})


async def _service_health() -> dict:
    """Health of the platform's own services for the dashboard's system panel. Cached for 5 s:
    the overview is refetched on every burst of real-time events by every open dashboard."""
    global _health_cache
    loop_now = asyncio.get_running_loop().time()
    if loop_now - _health_cache[0] < 5:
        return _health_cache[1]
    health: dict = {"api": "ok", "database": "ok"}
    r = get_redis()
    if r is None:
        health["redis"] = "not configured"
    else:
        try:
            await r.ping()
            health["redis"] = "ok"
            info = await r.xinfo_groups(get_settings().stream_ingest_key)
            health["ingest_backlog"] = sum(int(g.get("pending", 0)) + int(g.get("lag") or 0) for g in info)
        except Exception as exc:
            health.setdefault("redis", f"error: {exc.__class__.__name__}")
    if gateway.enabled:
        try:
            paths = await gateway.list_paths()
            health["gateway"] = "ok"
            health["gateway_streams_ready"] = sum(1 for p in paths if p.get("ready"))
            health["gateway_viewers"] = sum(len(p.get("readers") or []) for p in paths)
        except Exception as exc:
            health["gateway"] = f"error: {exc.__class__.__name__}"
    _health_cache = (loop_now, health)
    return health


@router.get("/stats/timeseries", tags=["stats"])
async def timeseries(hours: int = Query(24, ge=1, le=168), db: AsyncSession = DB, _: User = Depends(any_user)):
    """Hourly detections and alerts for the dashboard trend chart."""
    now = datetime.now(UTC)
    since = (now - timedelta(hours=hours - 1)).replace(minute=0, second=0, microsecond=0)
    dialect = db.bind.dialect.name

    def bucket(col):
        if dialect == "mysql":
            return func.date_format(col, "%Y-%m-%dT%H:00")
        return func.strftime("%Y-%m-%dT%H:00", col)

    async def counts(col, *where) -> dict[str, int]:
        b = bucket(col).label("bucket")
        rows = await db.execute(select(b, func.count()).where(col >= since, *where).group_by(b))
        return dict(rows.all())

    ev = await counts(DetectionEvent.detected_at)
    hits = await counts(DetectionEvent.detected_at, DetectionEvent.watchlist_hit.is_(True))
    al = await counts(Alert.triggered_at)
    series = []
    for i in range(hours):
        t = since + timedelta(hours=i)
        k = t.strftime("%Y-%m-%dT%H:00")
        series.append({"hour": t, "detections": ev.get(k, 0), "watchlist_hits": hits.get(k, 0), "alerts": al.get(k, 0)})
    return series


@router.get("/audit", tags=["audit"])
async def audit_log(
    entity_type: str | None = None,
    action: str | None = None,
    actor: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = DB,
    _: User = Depends(admin_only),
):
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor:
        stmt = stmt.where(AuditLog.actor_name == actor)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset))).scalars()
    return {
        "total": total,
        "items": [
            {
                "id": a.id,
                "created_at": a.created_at,
                "actor_type": a.actor_type,
                "actor_name": a.actor_name,
                "action": a.action,
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "details": a.details,
                "ip_address": a.ip_address,
            }
            for a in rows
        ],
    }


# --- Health & metrics ----------------------------------------------------------------------

health_router = APIRouter(tags=["system"])


@health_router.get("/health")
async def health():
    """Liveness probe."""
    return {"status": "ok"}


@health_router.get("/ready")
async def ready():
    """Readiness probe: database and Redis reachable."""
    checks = {}
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc.__class__.__name__}"
    r = get_redis()
    if r is not None:
        try:
            await r.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {exc.__class__.__name__}"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ready" if ok else "degraded", "checks": checks}, status_code=200 if ok else 503)


@health_router.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# --- WebSocket ------------------------------------------------------------------------------

ws_router = APIRouter()


@ws_router.websocket("/ws")
async def websocket(ws: WebSocket, token: str = Query("")):
    """Real-time channel. Messages: detection.created, alert.created, alert.updated,
    camera.status, camera.created, camera.updated, watchlist.changed."""
    try:
        payload = decode_token(token, "access")
    except jwt.PyJWTError:
        await ws.close(code=4401)
        return
    if await sessions.is_revoked(payload):
        await ws.close(code=4401)
        return
    async with SessionLocal() as db:
        user = await db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        await ws.close(code=4401)
        return
    await ws.accept()
    await manager.add(ws, {"id": user.id, "role": user.role})
    await ws.send_json({"type": "hello", "data": {"user": user.username, "role": user.role}})
    try:
        while True:
            msg = await asyncio.wait_for(ws.receive_text(), timeout=90)
            if msg == "ping":
                await ws.send_text('{"type":"pong"}')
    except (WebSocketDisconnect, TimeoutError, RuntimeError):
        pass
    finally:
        await manager.remove(ws)
        with contextlib.suppress(Exception):
            await ws.close()
