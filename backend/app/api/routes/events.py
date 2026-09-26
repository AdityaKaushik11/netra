import csv
import io
import math
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, Principal, any_user, operator_or_admin, principal_with
from app.models import Alert, Camera, DetectionEvent, User, WatchlistEntry
from app.models.enums import EventType, Role
from app.schemas import Page
from app.schemas.event import (
    BatchIngestResult,
    DetectionBatchIn,
    DetectionEventIn,
    DetectionEventOut,
    IngestResult,
    TraceOut,
    TraceStop,
    normalize_identifier,
)
from app.services.ingestion import IngestError, ingest
from app.services.serializers import event_out

router = APIRouter(tags=["analytics events"])

IMPOSSIBLE_SPEED_KMH = 160.0


@router.post(
    "/events",
    response_model=IngestResult,
    status_code=201,
    responses={200: {"description": "Duplicate (idempotent retry) or suppressed repeat read"}},
)
async def ingest_event(
    body: DetectionEventIn,
    response: Response,
    db: AsyncSession = DB,
    principal: Principal = Depends(principal_with("events:write", Role.ADMIN)),
):
    """Ingest one AI inference result (ANPR, vehicle/person/face/object detection).

    Pipeline: schema + semantic validation → idempotency on `event_id` → temporal de-duplication
    → persist → watchlist correlation → alert (with cool-down) → real-time WebSocket push."""
    try:
        result = await ingest(db, body, source_client=principal.name)
    except IngestError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from None
    if result.status != "created":
        response.status_code = 200
    return result


@router.post("/events/batch", response_model=BatchIngestResult)
async def ingest_batch(
    body: DetectionBatchIn,
    db: AsyncSession = DB,
    principal: Principal = Depends(principal_with("events:write", Role.ADMIN)),
):
    """Batch ingestion for edge gateways that buffer events during connectivity loss."""
    results: list[IngestResult] = []
    for ev in body.events:
        try:
            results.append(await ingest(db, ev, source_client=principal.name))
        except IngestError as exc:
            await db.rollback()
            results.append(IngestResult(status="rejected", detail=exc.detail))
    counts = Counter(r.status for r in results)
    return BatchIngestResult(
        results=results,
        created=counts["created"],
        duplicates=counts["duplicate"],
        suppressed=counts["suppressed"],
        rejected=counts["rejected"],
    )


def _filtered(
    camera_id: str | None,
    event_type: EventType | None,
    identifier: str | None,
    since: datetime | None,
    until: datetime | None,
    watchlist_hit: bool | None,
    min_confidence: float | None,
):
    stmt = select(DetectionEvent)
    if camera_id:
        stmt = stmt.where(DetectionEvent.camera_id == camera_id)
    if event_type:
        stmt = stmt.where(DetectionEvent.event_type == event_type)
    if identifier:
        norm = normalize_identifier(identifier)
        if norm:
            stmt = stmt.where(DetectionEvent.identifier_normalized.like(f"{norm}%"))
    if since:
        stmt = stmt.where(DetectionEvent.detected_at >= since)
    if until:
        stmt = stmt.where(DetectionEvent.detected_at <= until)
    if watchlist_hit is not None:
        stmt = stmt.where(DetectionEvent.watchlist_hit.is_(watchlist_hit))
    if min_confidence is not None:
        stmt = stmt.where(DetectionEvent.confidence >= min_confidence)
    return stmt


@router.get("/events", response_model=Page[DetectionEventOut])
async def list_events(
    camera_id: str | None = None,
    event_type: EventType | None = None,
    identifier: str | None = Query(None, max_length=20, description="Plate / person ref (prefix match)"),
    since: datetime | None = None,
    until: datetime | None = None,
    watchlist_hit: bool | None = None,
    min_confidence: float | None = Query(None, ge=0, le=1),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = DB,
    _: User = Depends(any_user),
):
    """Timestamped event history with filters (backed by composite indexes)."""
    stmt = _filtered(camera_id, event_type, identifier, since, until, watchlist_hit, min_confidence)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(DetectionEvent.detected_at.desc()).limit(limit).offset(offset))).scalars()
    return Page(items=[event_out(e) for e in rows], total=total or 0, limit=limit, offset=offset)


@router.get("/events/export.csv", response_class=StreamingResponse)
async def export_events(
    camera_id: str | None = None,
    event_type: EventType | None = None,
    identifier: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    watchlist_hit: bool | None = None,
    db: AsyncSession = DB,
    _: User = Depends(operator_or_admin),
):
    """CSV report of events (max 50k rows)."""
    stmt = _filtered(camera_id, event_type, identifier, since, until, watchlist_hit, None)
    rows = (await db.execute(stmt.order_by(DetectionEvent.detected_at.desc()).limit(50_000))).scalars()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "detected_at",
            "camera_id",
            "camera_name",
            "event_type",
            "identifier",
            "vehicle_type",
            "confidence",
            "repeat_count",
            "watchlist_hit",
            "latitude",
            "longitude",
        ]
    )
    for e in rows:
        w.writerow(
            [
                e.id,
                e.detected_at.isoformat(),
                e.camera_id,
                e.camera.name if e.camera else "",
                e.event_type,
                e.identifier or "",
                e.vehicle_type or "",
                f"{e.confidence:.3f}",
                e.repeat_count,
                e.watchlist_hit,
                e.latitude,
                e.longitude,
            ]
        )
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=netra-events.csv"},
    )


@router.get("/events/{event_id}", response_model=DetectionEventOut)
async def get_event(event_id: int, db: AsyncSession = DB, _: User = Depends(any_user)):
    e = await db.get(DetectionEvent, event_id)
    if not e:
        raise HTTPException(status_code=404, detail="Event not found")
    return event_out(e)


# --- Entity search & movement trace ---------------------------------------------------------


@router.get("/search", tags=["search & trace"])
async def search(
    q: str = Query(min_length=2, max_length=32),
    db: AsyncSession = DB,
    _: User = Depends(any_user),
):
    """Universal search across detected entities (plates / person refs), watchlist and cameras."""
    norm = normalize_identifier(q) or ""
    entities = []
    if norm:
        rows = await db.execute(
            select(
                DetectionEvent.identifier_normalized,
                func.max(DetectionEvent.identifier),
                func.count(),
                func.max(DetectionEvent.detected_at),
                func.count(func.distinct(DetectionEvent.camera_id)),
            )
            .where(DetectionEvent.identifier_normalized.like(f"%{norm}%"))
            .group_by(DetectionEvent.identifier_normalized)
            .order_by(func.max(DetectionEvent.detected_at).desc())
            .limit(20)
        )
        entities = [
            {"identifier_normalized": n, "identifier": ident, "detections": c, "last_seen": ls, "cameras": cams}
            for n, ident, c, ls, cams in rows.all()
        ]
    watch = []
    if norm:  # input like "--" normalises to nothing and would otherwise match every entry
        stmt = select(WatchlistEntry).where(WatchlistEntry.identifier_normalized.like(f"%{norm}%")).limit(10)
        watch = (await db.execute(stmt)).scalars().all()
    like = f"%{q}%"
    cams = (
        await db.execute(select(Camera).where(or_(Camera.id.ilike(like), Camera.name.ilike(like))).limit(10))
    ).scalars()
    return {
        "entities": entities,
        "watchlist": [
            {
                "id": w.id,
                "identifier": w.identifier,
                "category": w.category,
                "severity": w.severity,
                "is_active": w.is_active,
            }
            for w in watch
        ],
        "cameras": [{"id": c.id, "name": c.name, "status": c.status, "zone": c.zone} for c in cams],
    }


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@router.get("/trace/{identifier}", response_model=TraceOut, tags=["search & trace"])
async def trace(
    identifier: str,
    since: datetime | None = None,
    until: datetime | None = None,
    db: AsyncSession = DB,
    _: User = Depends(any_user),
):
    """Chronological movement history of a vehicle/person across cameras, with leg distances,
    implied speeds and anomaly flags (e.g. physically impossible travel → possible cloned plate)."""
    norm = normalize_identifier(identifier)
    if not norm:
        raise HTTPException(status_code=422, detail="Invalid identifier")
    stmt = select(DetectionEvent).where(DetectionEvent.identifier_normalized == norm)
    if since:
        stmt = stmt.where(DetectionEvent.detected_at >= since)
    if until:
        stmt = stmt.where(DetectionEvent.detected_at <= until)
    # Most recent 2000 sightings, returned oldest-first
    latest = (await db.execute(stmt.order_by(DetectionEvent.detected_at.desc()).limit(2000))).scalars().all()
    events = list(reversed(latest))

    stops: list[TraceStop] = []
    anomalies: list[str] = []
    total_km = 0.0
    prev: DetectionEvent | None = None
    for e in events:
        minutes = dist = speed = None
        if prev is not None:
            minutes = (e.detected_at - prev.detected_at).total_seconds() / 60
            dist = haversine_km(prev.latitude, prev.longitude, e.latitude, e.longitude)
            total_km += dist
            if minutes > 0:
                speed = dist / (minutes / 60)
            if dist > 1 and (minutes <= 0 or (speed or 0) > IMPOSSIBLE_SPEED_KMH):
                anomalies.append(
                    f"Impossible travel {prev.camera_id}→{e.camera_id}: {dist:.1f} km in {minutes:.1f} min "
                    f"— possible cloned/duplicate plate"
                )
        stops.append(
            TraceStop(
                event_id=e.id,
                camera_id=e.camera_id,
                camera_name=e.camera.name if e.camera else e.camera_id,
                zone=e.camera.zone if e.camera else None,
                latitude=e.latitude,
                longitude=e.longitude,
                detected_at=e.detected_at,
                confidence=e.confidence,
                repeat_count=e.repeat_count,
                minutes_since_previous=round(minutes, 1) if minutes is not None else None,
                distance_km_from_previous=round(dist, 2) if dist is not None else None,
                implied_speed_kmh=round(speed, 1) if speed is not None else None,
            )
        )
        prev = e

    watch = await db.scalar(select(WatchlistEntry).where(WatchlistEntry.identifier_normalized == norm))
    total_alerts = 0
    if watch:
        total_alerts = (
            await db.scalar(select(func.count()).select_from(Alert).where(Alert.watchlist_entry_id == watch.id)) or 0
        )
    return TraceOut(
        identifier=events[-1].identifier if events else identifier.upper(),
        identifier_normalized=norm,
        first_seen=events[0].detected_at if events else None,
        last_seen=events[-1].detected_at if events else None,
        total_detections=len(events),
        distinct_cameras=len({e.camera_id for e in events}),
        total_distance_km=round(total_km, 2),
        watchlist=(
            {
                "id": watch.id,
                "category": watch.category,
                "severity": watch.severity,
                "description": watch.description,
                "case_reference": watch.case_reference,
                "is_active": watch.is_active,
                "alerts": total_alerts,
            }
            if watch
            else None
        ),
        stops=stops,
        anomalies=anomalies,
    )
