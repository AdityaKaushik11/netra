"""Analytics ingestion pipeline — the heart of the platform.

    validate -> idempotency -> temporal dedup -> persist -> watchlist correlation
             -> alert (with cool-down) -> commit -> real-time publish

The same pipeline serves the REST API, the batch API and the Redis Stream consumer.
"""

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from prometheus_client import Counter, Histogram
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Alert, Camera, DetectionEvent
from app.models.enums import (
    AlertStatus,
    EntityType,
    EventType,
    MatchType,
    downgrade,
)
from app.schemas.event import INDIAN_PLATE, DetectionEventIn, IngestResult, normalize_identifier
from app.services import audit, dedup, event_bus
from app.services.serializers import alert_out, event_out
from app.services.watchlist_matcher import Match, matcher

log = logging.getLogger(__name__)

EVENTS_TOTAL = Counter("netra_events_total", "Analytics events processed", ["event_type", "result"])
ALERTS_TOTAL = Counter("netra_alerts_total", "Alerts raised", ["severity", "match_type"])
INGEST_LATENCY = Histogram(
    "netra_ingest_seconds", "Ingestion pipeline latency", buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1)
)

VEHICLE_EVENTS = {EventType.ANPR, EventType.VEHICLE_DETECTION}
PERSON_EVENTS = {EventType.FACE_RECOGNITION, EventType.PERSON_DETECTION}

CATEGORY_LABEL = {
    "STOLEN_VEHICLE": "Stolen vehicle",
    "BLACKLISTED_VEHICLE": "Blacklisted vehicle",
    "WANTED_PERSON": "Wanted person",
    "MISSING_PERSON": "Missing person",
    "SUSPICIOUS": "Entity of interest",
}


class IngestError(Exception):
    def __init__(self, detail: str, status_code: int = 422):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _entity_type(event_type: EventType) -> EntityType | None:
    if event_type in VEHICLE_EVENTS:
        return EntityType.VEHICLE
    if event_type in PERSON_EVENTS:
        return EntityType.PERSON
    return None


async def ingest(db: AsyncSession, payload: DetectionEventIn, source_client: str) -> IngestResult:
    started = time.perf_counter()
    try:
        result = await _ingest(db, payload, source_client)
    except IngestError:
        EVENTS_TOTAL.labels(payload.event_type, "rejected").inc()
        raise
    EVENTS_TOTAL.labels(payload.event_type, result.status).inc()
    INGEST_LATENCY.observe(time.perf_counter() - started)
    return result


async def _ingest(db: AsyncSession, p: DetectionEventIn, source_client: str) -> IngestResult:
    s = get_settings()
    now = datetime.now(UTC)

    # 1. Semantic validation (schema validation already happened in Pydantic)
    camera = await db.get(Camera, p.camera_id)
    if camera is None:
        raise IngestError(f"Unknown camera_id '{p.camera_id}'", 404)
    if not camera.is_enabled:
        raise IngestError(f"Camera '{p.camera_id}' is disabled", 409)
    detected_at = p.timestamp.astimezone(UTC)
    if detected_at > now + timedelta(seconds=s.max_future_skew_seconds):
        raise IngestError("timestamp is in the future beyond allowed clock skew")
    if detected_at < now - timedelta(hours=s.max_event_age_hours):
        raise IngestError(f"timestamp older than {s.max_event_age_hours}h; use the backfill process")

    # 2. Idempotency: producer retries with the same event_id never create a second row
    event_uid = p.event_id or uuid.uuid4().hex
    if p.event_id:
        existing_id = await db.scalar(select(DetectionEvent.id).where(DetectionEvent.event_uid == p.event_id))
        if existing_id:
            return IngestResult(status="duplicate", event_id=existing_id, event_uid=p.event_id)

    identifier = p.identifier
    identifier_norm = normalize_identifier(identifier)

    # 3. Temporal de-duplication (same camera + type + identity inside the window)
    key = None
    if identifier_norm:
        key = dedup.dedup_key(camera.id, p.event_type, identifier_norm)
        holder = await dedup.claim(key, event_uid)
        if holder is not None:
            original = await db.scalar(select(DetectionEvent).where(DetectionEvent.event_uid == holder))
            if original is not None:
                last_seen = max(original.last_seen_at or original.detected_at, detected_at)
                await db.execute(
                    update(DetectionEvent)
                    .where(DetectionEvent.id == original.id)
                    .values(
                        repeat_count=DetectionEvent.repeat_count + 1,
                        last_seen_at=last_seen,
                        confidence=max(original.confidence, p.confidence),
                    )
                )
                await db.commit()
                return IngestResult(
                    status="suppressed",
                    event_id=original.id,
                    event_uid=original.event_uid,
                    detail="duplicate read folded into existing event",
                )
            # Holder not persisted (still in flight or failed) — take over the key
            await dedup.update(key, event_uid)

    # 4. Persist
    attributes = dict(p.attributes or {})
    if p.speed_kmh is not None:
        attributes["speed_kmh"] = p.speed_kmh
    # Mobile cameras report where the frame was captured; fixed cameras use the registry location
    lat = p.latitude if p.latitude is not None else camera.latitude
    lng = p.longitude if p.longitude is not None else camera.longitude
    if p.event_type == EventType.ANPR and identifier_norm:
        attributes["plate_format_valid"] = bool(INDIAN_PLATE.match(identifier_norm))
    event = DetectionEvent(
        event_uid=event_uid,
        camera_id=camera.id,
        event_type=p.event_type,
        detected_at=detected_at,
        received_at=now,
        identifier=identifier.strip().upper() if identifier else None,
        identifier_normalized=identifier_norm,
        vehicle_type=p.vehicle_type,
        vehicle_color=p.vehicle_color,
        object_label=p.object_label,
        confidence=p.confidence,
        bounding_box=p.bounding_box.model_dump() if p.bounding_box else None,
        snapshot_url=p.snapshot_url,
        model_name=p.model_name,
        source_client=source_client,
        attributes=attributes or None,
        latitude=lat,
        longitude=lng,
        repeat_count=0,
    )
    event.camera = camera
    db.add(event)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        if key:
            await dedup.release(key)
        existing_id = await db.scalar(select(DetectionEvent.id).where(DetectionEvent.event_uid == event_uid))
        return IngestResult(status="duplicate", event_id=existing_id, event_uid=event_uid)

    # 5. Watchlist correlation
    new_alerts: list[Alert] = []
    updated_alerts: list[Alert] = []
    entity_type = _entity_type(p.event_type)
    if identifier_norm and entity_type and p.confidence >= s.min_match_confidence:
        await matcher.ensure_loaded(db)
        for m in matcher.match(entity_type, identifier_norm):
            alert, created = await _raise_or_update_alert(db, event, camera, m, now)
            (new_alerts if created else updated_alerts).append(alert)
        event.watchlist_hit = bool(new_alerts or updated_alerts)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        if key:
            await dedup.release(key)
        raise

    # 6. Real-time publish (after commit, so clients never see uncommitted data)
    await event_bus.publish("detection.created", event_out(event))
    for a in new_alerts:
        ALERTS_TOTAL.labels(a.severity, a.match_type).inc()
        await event_bus.publish("alert.created", alert_out(a))
    for a in updated_alerts:
        await event_bus.publish("alert.updated", alert_out(a))

    return IngestResult(
        status="created",
        event_id=event.id,
        event_uid=event.event_uid,
        alert_ids=[a.id for a in new_alerts + updated_alerts],
    )


async def _raise_or_update_alert(
    db: AsyncSession, event: DetectionEvent, camera: Camera, m: Match, now: datetime
) -> tuple[Alert, bool]:
    """Alert storm protection: an open alert for the same entity at the same camera inside the
    cool-down window is updated (hit_count++) instead of raising a new one."""
    s = get_settings()
    cutoff = now - timedelta(seconds=s.alert_cooldown_seconds)
    existing = await db.scalar(
        select(Alert)
        .where(
            Alert.watchlist_entry_id == m.entry.id,
            Alert.camera_id == camera.id,
            Alert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED]),
            Alert.last_hit_at >= cutoff,
        )
        .order_by(Alert.last_hit_at.desc())
        .limit(1)
    )
    if existing is not None:
        existing.hit_count += 1
        existing.last_hit_at = now
        existing.confidence = max(existing.confidence, event.confidence)
        await db.flush()
        return existing, False

    severity = m.entry.severity if m.match_type == MatchType.EXACT else downgrade(m.entry.severity)
    label = CATEGORY_LABEL.get(m.entry.category, "Watchlist match")
    prefix = "" if m.match_type == MatchType.EXACT else "Possible "
    alert = Alert(
        event_id=event.id,
        watchlist_entry_id=m.entry.id,
        camera_id=camera.id,
        identifier=event.identifier or m.entry.identifier,
        identifier_normalized=event.identifier_normalized or m.entry.identifier_normalized,
        match_type=m.match_type,
        confidence=event.confidence,
        severity=severity,
        status=AlertStatus.NEW,
        title=f"{prefix}{label.lower() if prefix else label} {m.entry.identifier} at {camera.name}",
        latitude=event.latitude,
        longitude=event.longitude,
        triggered_at=now,
        last_hit_at=now,
        hit_count=1,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert, ["camera", "event", "watchlist_entry"])
    audit.record(
        db,
        audit.Actor.system("correlation-engine"),
        "ALERT_RAISED",
        "alert",
        alert.id,
        {
            "watchlist_entry_id": m.entry.id,
            "event_id": event.id,
            "camera_id": camera.id,
            "match_type": m.match_type,
            "detected": event.identifier,
            "watchlisted": m.entry.identifier,
        },
    )
    return alert, True
