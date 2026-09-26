"""Camera health monitor.

Runs inside every API replica but only the replica holding a Redis leader lock does the work,
so probes are not multiplied by the number of replicas. Status changes are persisted, audited
and pushed to dashboards in real time. A simple hysteresis (two consecutive failures before
OFFLINE) prevents marker flapping on a single lost probe.
"""

import asyncio
import contextlib
import logging
import socket
from datetime import UTC, datetime, timedelta

from prometheus_client import Gauge
from sqlalchemy import delete, select

from app.adapters import ProbeResult, get_adapter
from app.core.config import get_settings
from app.db import SessionLocal
from app.models import Alert, Camera, CameraPosition, DetectionEvent
from app.models.enums import CameraStatus, HealthMode, SourceProtocol
from app.services import audit, event_bus
from app.services.gateway import gateway
from app.services.redis_client import get_redis
from app.services.serializers import camera_out

log = logging.getLogger(__name__)
GATEWAY_PROTOCOLS = (SourceProtocol.RTSP, SourceProtocol.ONVIF)
LEADER_KEY = "netra:leader:health-monitor"
CAMERA_STATUS = Gauge("netra_cameras", "Cameras by status", ["status"])
_failures: dict[str, int] = {}
_instance_id = f"{socket.gethostname()}"


async def _is_leader(ttl: int) -> bool:
    r = get_redis()
    if r is None:
        return True
    if await r.set(LEADER_KEY, _instance_id, nx=True, ex=ttl):
        return True
    if await r.get(LEADER_KEY) == _instance_id:
        await r.expire(LEADER_KEY, ttl)
        return True
    return False


def heartbeat_status(camera: Camera, now: datetime) -> ProbeResult:
    s = get_settings()
    if camera.last_heartbeat_at is None:
        return ProbeResult(CameraStatus.OFFLINE, "no heartbeat received yet")
    age = (now - camera.last_heartbeat_at).total_seconds()
    metrics = dict(camera.health_metrics or {})
    metrics["heartbeat_age_s"] = round(age, 1)
    if age > s.heartbeat_offline_after_s:
        return ProbeResult(CameraStatus.OFFLINE, f"heartbeat lost ({int(age)}s)", metrics)
    if age > s.heartbeat_degraded_after_s:
        return ProbeResult(CameraStatus.DEGRADED, f"heartbeat late ({int(age)}s)", metrics)
    loss = metrics.get("packet_loss_pct") or 0
    fps = metrics.get("fps")
    if loss > 5 or (fps is not None and fps < 5):
        return ProbeResult(CameraStatus.DEGRADED, "edge reports packet loss / low fps", metrics)
    return ProbeResult(CameraStatus.ONLINE, "heartbeat OK", metrics)


async def _probe(camera: Camera) -> ProbeResult:
    try:
        return await get_adapter(camera.source_protocol).probe(camera)
    except Exception as exc:  # a broken adapter must never kill the monitor loop
        log.exception("probe crashed for %s", camera.id)
        return ProbeResult(CameraStatus.UNKNOWN, f"probe error: {exc.__class__.__name__}")


async def evaluate(camera: Camera) -> ProbeResult:
    now = datetime.now(UTC)
    if camera.health_mode != HealthMode.HEARTBEAT:
        return await _probe(camera)
    result = heartbeat_status(camera, now)
    # A live device whose video cannot be pulled is not healthy: check the stream as well
    if result.status == CameraStatus.ONLINE and camera.source_protocol in GATEWAY_PROTOCOLS and gateway.enabled:
        video = await _probe(camera)
        if video.status == CameraStatus.OFFLINE:
            return ProbeResult(
                CameraStatus.DEGRADED, f"heartbeat OK, video unavailable ({video.reason})", result.metrics
            )
    return result


async def apply_result(db, camera: Camera, result: ProbeResult) -> bool:
    """Persist a probe result. Returns True when the status changed."""
    now = datetime.now(UTC)
    status = result.status
    if status == CameraStatus.OFFLINE and camera.health_mode == HealthMode.PROBE:
        _failures[camera.id] = _failures.get(camera.id, 0) + 1
        if _failures[camera.id] < 2 and camera.status in (CameraStatus.ONLINE, CameraStatus.DEGRADED):
            status = CameraStatus.DEGRADED
            result.reason = f"probe failed, retrying ({result.reason})"
    else:
        _failures.pop(camera.id, None)

    if camera.health_mode == HealthMode.PROBE:
        camera.health_metrics = result.metrics or None
        if status in (CameraStatus.ONLINE, CameraStatus.DEGRADED):
            camera.last_heartbeat_at = now
    changed = status != camera.status
    if changed:
        audit.record(
            db,
            audit.Actor.system("health-monitor"),
            "CAMERA_STATUS_CHANGED",
            "camera",
            camera.id,
            {"from": camera.status, "to": status, "reason": result.reason},
        )
        camera.status = status
        camera.status_changed_at = now
    camera.status_reason = result.reason
    return changed


async def run_cycle() -> None:
    sem = asyncio.Semaphore(32)
    async with SessionLocal() as db:
        cameras = list((await db.execute(select(Camera).where(Camera.is_enabled.is_(True)))).scalars())

        async def probe(c: Camera) -> tuple[Camera, ProbeResult]:
            async with sem:
                return c, await evaluate(c)

        results = await asyncio.gather(*(probe(c) for c in cameras))
        changed = [c for c, r in results if await apply_result(db, c, r)]
        await db.commit()
        counts: dict[str, int] = {s.value: 0 for s in CameraStatus}
        for c in cameras:
            counts[c.status] += 1
        for k, v in counts.items():
            CAMERA_STATUS.labels(k).set(v)
    for c in changed:
        log.info("camera %s -> %s (%s)", c.id, c.status, c.status_reason)
        await event_bus.publish("camera.status", camera_out(c))


async def prune_old_data() -> None:
    """Retention so a long-running deployment never fills its disk: dashcam GPS points after
    POSITION_RETENTION_HOURS, detection events after EVENT_RETENTION_DAYS. Events referenced by
    an alert are kept (alerts are evidence); audit logs are never pruned."""
    s = get_settings()
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await db.execute(
            delete(CameraPosition).where(CameraPosition.recorded_at < now - timedelta(hours=s.position_retention_hours))
        )
        alerted = select(Alert.event_id)
        while True:  # delete in batches to keep transactions and locks small
            ids = (
                (
                    await db.execute(
                        select(DetectionEvent.id)
                        .where(
                            DetectionEvent.detected_at < now - timedelta(days=s.event_retention_days),
                            DetectionEvent.id.not_in(alerted),
                        )
                        .limit(5000)
                    )
                )
                .scalars()
                .all()
            )
            if not ids:
                break
            await db.execute(delete(DetectionEvent).where(DetectionEvent.id.in_(ids)))
            await db.commit()
        await db.commit()


async def run_monitor(stop: asyncio.Event) -> None:
    s = get_settings()
    await asyncio.sleep(2)
    cycles = 0
    while not stop.is_set():
        try:
            if await _is_leader(ttl=s.health_interval_seconds * 3):
                await run_cycle()
                if cycles % 360 == 0:  # roughly hourly
                    await prune_old_data()
                cycles += 1
        except Exception:
            log.exception("health monitor cycle failed")
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=s.health_interval_seconds)
