import asyncio
import hmac
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import jwt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import get_adapter
from app.adapters.http_sources import VendorApiAdapter, safe_get
from app.adapters.onvif import OnvifError, get_device_information, get_stream_uri
from app.api.deps import DB, Principal, admin_only, any_user, operator_or_admin, principal_with, user_actor
from app.core.config import get_settings
from app.core.netguard import UnsafeTarget
from app.core.security import create_stream_token, decode_token, encrypt_secret
from app.db import SessionLocal
from app.models import Alert, AuditLog, Camera, CameraPosition, User
from app.models.enums import (
    AlertStatus,
    CameraStatus,
    CameraType,
    HealthMode,
    OnboardingSource,
    Role,
    SourceProtocol,
)
from app.schemas import Page
from app.schemas.camera import (
    BulkResult,
    CameraBulkCreate,
    CameraCreate,
    CameraOut,
    CameraUpdate,
    HeartbeatIn,
    OnvifDiscoveredDevice,
    OnvifDiscoverIn,
    PlaybackInfo,
    RecordingSegment,
    TrackPoint,
    check_scheme,
)
from app.services import audit, event_bus
from app.services.gateway import gateway, path_name
from app.services.health_monitor import apply_result, evaluate, heartbeat_status
from app.services.serializers import camera_out

log = logging.getLogger(__name__)
router = APIRouter(tags=["cameras"])

OPEN = [AlertStatus.NEW, AlertStatus.ACKNOWLEDGED]
SECRET_FIELDS = {"stream_password"}
NON_NULLABLE = {
    "name",
    "latitude",
    "longitude",
    "camera_type",
    "stream_endpoint",
    "recording_enabled",
    "retention_days",
    "health_mode",
    "is_enabled",
}


async def _open_alert_counts(db: AsyncSession, ids: list[str] | None = None) -> dict[str, int]:
    q = select(Alert.camera_id, func.count()).where(Alert.status.in_(OPEN)).group_by(Alert.camera_id)
    if ids is not None:
        q = q.where(Alert.camera_id.in_(ids))
    return dict((await db.execute(q)).all())


async def _get_camera(db: AsyncSession, camera_id: str) -> Camera:
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return camera


async def _probe_now(camera_id: str) -> None:
    async with SessionLocal() as db:
        camera = await db.get(Camera, camera_id)
        if camera is None or not camera.is_enabled:
            return
        changed = await apply_result(db, camera, await evaluate(camera))
        await db.commit()
        if changed:
            await event_bus.publish("camera.status", camera_out(camera))


@router.get("/cameras", response_model=Page[CameraOut])
async def list_cameras(
    q: str | None = Query(None, max_length=64, description="Search id, name, zone, address"),
    status: CameraStatus | None = None,
    department_id: int | None = None,
    zone: str | None = None,
    protocol: SourceProtocol | None = None,
    camera_type: CameraType | None = None,
    enabled: bool | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = DB,
    _: User = Depends(any_user),
):
    stmt = select(Camera)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Camera.id.ilike(like), Camera.name.ilike(like), Camera.zone.ilike(like), Camera.address.ilike(like))
        )
    if status:
        stmt = stmt.where(Camera.status == status)
    if department_id:
        stmt = stmt.where(Camera.department_id == department_id)
    if zone:
        stmt = stmt.where(Camera.zone == zone)
    if protocol:
        stmt = stmt.where(Camera.source_protocol == protocol)
    if camera_type:
        stmt = stmt.where(Camera.camera_type == camera_type)
    if enabled is not None:
        stmt = stmt.where(Camera.is_enabled.is_(enabled))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(Camera.id).limit(limit).offset(offset))).scalars().all()
    counts = await _open_alert_counts(db, [c.id for c in rows])
    return Page(items=[camera_out(c, counts.get(c.id, 0)) for c in rows], total=total or 0, limit=limit, offset=offset)


@router.get("/cameras/zones", response_model=list[str])
async def list_zones(db: AsyncSession = DB, _: User = Depends(any_user)):
    rows = await db.execute(select(Camera.zone).where(Camera.zone.is_not(None)).distinct().order_by(Camera.zone))
    return [z for (z,) in rows.all()]


@router.get("/cameras/{camera_id}", response_model=CameraOut)
async def get_camera(camera_id: str, db: AsyncSession = DB, _: User = Depends(any_user)):
    camera = await _get_camera(db, camera_id)
    counts = await _open_alert_counts(db, [camera_id])
    return camera_out(camera, counts.get(camera_id, 0))


async def _create(db: AsyncSession, body: CameraCreate, principal: Principal, source: OnboardingSource) -> Camera:
    if await db.get(Camera, body.id):
        raise HTTPException(status_code=409, detail=f"Camera {body.id} already exists")
    data = body.model_dump(exclude={"stream_password", "id"})
    camera = Camera(
        id=body.id,
        **data,
        stream_secret_enc=encrypt_secret(body.stream_password),
        status=CameraStatus.UNKNOWN,
        onboarding_source=source,
        is_enabled=True,
    )
    await get_adapter(camera.source_protocol).prepare(camera)
    db.add(camera)
    audit.record(
        db,
        principal.actor,
        "CAMERA_ONBOARDED",
        "camera",
        camera.id,
        {"protocol": camera.source_protocol, "source": source, "endpoint": camera.stream_endpoint},
    )
    return camera


@router.post("/cameras", response_model=CameraOut, status_code=201)
async def create_camera(
    body: CameraCreate,
    background: BackgroundTasks,
    db: AsyncSession = DB,
    principal: Principal = Depends(principal_with("cameras:write", Role.ADMIN)),
):
    """Onboard a camera — manually from the UI (admin JWT) or programmatically (API key with
    `cameras:write`). Credentials are encrypted at rest and never returned."""
    source = OnboardingSource.MANUAL if principal.user else OnboardingSource.API
    camera = await _create(db, body, principal, source)
    await db.commit()
    await db.refresh(camera)
    out = camera_out(camera)
    await event_bus.publish("camera.created", out)
    background.add_task(_probe_now, camera.id)
    return out


@router.post("/cameras/bulk", response_model=BulkResult)
async def bulk_create(
    body: CameraBulkCreate,
    background: BackgroundTasks,
    db: AsyncSession = DB,
    principal: Principal = Depends(principal_with("cameras:write", Role.ADMIN)),
):
    """API-based bulk onboarding (e.g. importing a department's existing CCTV inventory)."""
    created, errors = [], {}
    for item in body.cameras:
        try:
            async with db.begin_nested():
                await _create(db, item, principal, OnboardingSource.API)
            created.append(item.id)
        except HTTPException as exc:
            errors[item.id] = exc.detail
    await db.commit()
    for cid in created:
        background.add_task(_probe_now, cid)
    if created:
        await event_bus.publish("camera.bulk_created", {"ids": created})
    return BulkResult(created=created, errors=errors)


@router.patch("/cameras/{camera_id}", response_model=CameraOut)
async def update_camera(
    camera_id: str,
    body: CameraUpdate,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = DB,
    admin: User = Depends(admin_only),
):
    camera = await _get_camera(db, camera_id)
    changes = body.model_dump(exclude_unset=True)
    nulled = sorted(k for k in NON_NULLABLE if k in changes and changes[k] is None)
    if nulled:
        raise HTTPException(status_code=422, detail=f"Fields cannot be null: {', '.join(nulled)}")
    if "stream_endpoint" in changes:
        try:
            check_scheme(camera.source_protocol, changes["stream_endpoint"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from None
    before = {k: getattr(camera, k, None) for k in changes if k not in SECRET_FIELDS}
    source_changed = any(
        k in changes for k in ("stream_endpoint", "stream_username", "stream_password", "recording_enabled")
    )
    was_enabled = camera.is_enabled
    for key, value in changes.items():
        if key == "stream_password":
            camera.stream_secret_enc = encrypt_secret(value)
        else:
            setattr(camera, key, value)
    adapter = get_adapter(camera.source_protocol)
    if was_enabled and not camera.is_enabled:
        await adapter.teardown(camera)
        camera.status = CameraStatus.OFFLINE
        camera.status_reason = "disabled by administrator"
    elif camera.is_enabled and (source_changed or not was_enabled):
        camera.resolved_stream_uri = None
        await adapter.prepare(camera)
    details = audit.diff(before, {k: v for k, v in changes.items() if k not in SECRET_FIELDS})
    if "stream_password" in changes:
        details["stream_password"] = {"from": "***", "to": "*** (rotated)"}
    action = "CAMERA_UPDATED"
    if changes.keys() == {"is_enabled"}:
        action = "CAMERA_ENABLED" if camera.is_enabled else "CAMERA_DISABLED"
    audit.record(db, user_actor(admin, request), action, "camera", camera.id, details)
    await db.commit()
    await db.refresh(camera)
    out = camera_out(camera, (await _open_alert_counts(db, [camera_id])).get(camera_id, 0))
    await event_bus.publish("camera.updated", out)
    if camera.is_enabled:
        background.add_task(_probe_now, camera.id)
    return out


@router.get("/cameras/{camera_id}/audit")
async def camera_audit(
    camera_id: str, limit: int = Query(100, le=500), db: AsyncSession = DB, _: User = Depends(any_user)
):
    rows = await db.execute(
        select(AuditLog)
        .where(AuditLog.entity_type == "camera", AuditLog.entity_id == camera_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": a.id,
            "created_at": a.created_at,
            "actor_type": a.actor_type,
            "actor_name": a.actor_name,
            "action": a.action,
            "details": a.details,
        }
        for a in rows.scalars()
    ]


@router.post("/cameras/{camera_id}/heartbeat", status_code=202)
async def heartbeat(
    camera_id: str,
    body: HeartbeatIn,
    db: AsyncSession = DB,
    principal: Principal = Depends(principal_with("cameras:heartbeat", Role.ADMIN)),
):
    """Heartbeat from an edge agent / NVR / dashcam. Drives health for cameras in HEARTBEAT mode.
    Mobile cameras (dashcams) include GPS: the camera's position is updated, the fix is appended
    to its track and pushed to dashboards so the marker moves live."""
    camera = await _get_camera(db, camera_id)
    now = datetime.now(UTC)
    camera.last_heartbeat_at = now
    gps = {"latitude", "longitude", "speed_kmh", "heading_deg"}
    camera.health_metrics = {**(camera.health_metrics or {}), **body.model_dump(exclude_none=True, exclude=gps)}
    moved = body.latitude is not None and body.longitude is not None
    if moved:
        camera.latitude, camera.longitude = body.latitude, body.longitude
        camera.speed_kmh, camera.heading_deg = body.speed_kmh, body.heading_deg
        camera.location_updated_at = now
        db.add(
            CameraPosition(
                camera_id=camera.id,
                recorded_at=now,
                latitude=body.latitude,
                longitude=body.longitude,
                speed_kmh=body.speed_kmh,
                heading_deg=body.heading_deg,
            )
        )
    # Fast recovery only: a heartbeat brings an OFFLINE camera back immediately; the health
    # monitor owns every other transition (it also checks the video stream).
    changed = False
    if (
        camera.health_mode == HealthMode.HEARTBEAT
        and camera.is_enabled
        and camera.status in (CameraStatus.OFFLINE, CameraStatus.UNKNOWN)
    ):
        changed = await apply_result(db, camera, heartbeat_status(camera, now))
    await db.commit()
    if changed:
        await event_bus.publish("camera.status", camera_out(camera))
    if moved:
        await event_bus.publish(
            "camera.location",
            {
                "id": camera.id,
                "latitude": camera.latitude,
                "longitude": camera.longitude,
                "speed_kmh": camera.speed_kmh,
                "heading_deg": camera.heading_deg,
                "at": now,
            },
        )
    return {"status": camera.status, "accepted": True}


@router.get("/cameras/{camera_id}/track", response_model=list[TrackPoint])
async def camera_track(
    camera_id: str,
    minutes: int = Query(30, ge=1, le=1440),
    db: AsyncSession = DB,
    _: User = Depends(any_user),
):
    """GPS track of a mobile camera (dashcam) for the last `minutes`."""
    since = datetime.now(UTC) - timedelta(minutes=minutes)
    rows = await db.execute(
        select(CameraPosition)
        .where(CameraPosition.camera_id == camera_id, CameraPosition.recorded_at >= since)
        .order_by(CameraPosition.recorded_at)
        .limit(5000)
    )
    return [
        TrackPoint(
            t=p.recorded_at,
            latitude=p.latitude,
            longitude=p.longitude,
            speed_kmh=p.speed_kmh,
            heading_deg=p.heading_deg,
        )
        for p in rows.scalars()
    ]


def _require_recordable(camera: Camera) -> str:
    if camera.source_protocol not in (SourceProtocol.RTSP, SourceProtocol.ONVIF) or not camera.gateway_path:
        raise HTTPException(
            status_code=400, detail="Recording is only available for gateway-relayed (RTSP/ONVIF) cameras"
        )
    if not camera.recording_enabled:
        raise HTTPException(status_code=409, detail="Recording is disabled for this camera")
    return camera.gateway_path


@router.get("/cameras/{camera_id}/recordings", response_model=list[RecordingSegment])
async def recordings(camera_id: str, db: AsyncSession = DB, user: User = Depends(any_user)):
    """Recorded segments held by the video gateway (hot tier)."""
    camera = await _get_camera(db, camera_id)
    path = _require_recordable(camera)
    token, _ = create_stream_token(str(user.id), camera.id)
    try:
        items = await gateway.list_recordings(path, token)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Video gateway unavailable") from None
    return [RecordingSegment(start=i["start"], duration=i["duration"]) for i in items]


@router.get("/cameras/{camera_id}/clip", response_model=PlaybackInfo)
async def clip(
    camera_id: str,
    request: Request,
    start: datetime | None = Query(None, description="Clip start (default: 60 s ago)"),
    duration: int = Query(30, ge=5, le=600),
    db: AsyncSession = DB,
    user: User = Depends(any_user),
):
    """Recorded footage for a time window (evidence review / alert context), served as MP4 by the
    gateway playback server and authorised with a camera-scoped token."""
    camera = await _get_camera(db, camera_id)
    path = _require_recordable(camera)
    start = (start or datetime.now(UTC) - timedelta(seconds=60)).astimezone(UTC)
    token, exp = create_stream_token(str(user.id), camera.id)
    audit.record(
        db,
        user_actor(user, request),
        "RECORDING_ACCESSED",
        "camera",
        camera.id,
        {"start": start.isoformat(), "duration": duration},
    )
    await db.commit()
    base = get_settings().gateway_public_playback_base.rstrip("/")
    ts = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    return PlaybackInfo(
        camera_id=camera.id,
        kind="clip",
        url=f"{base}/get?path={path}&start={ts}&duration={duration}&format=mp4",
        token=token,
        expires_at=exp,
        note=f"Recorded {duration}s from {ts}",
    )


@router.post("/cameras/{camera_id}/probe", response_model=CameraOut)
async def probe_camera(camera_id: str, db: AsyncSession = DB, _: User = Depends(operator_or_admin)):
    camera = await _get_camera(db, camera_id)
    changed = await apply_result(db, camera, await evaluate(camera))
    await db.commit()
    out = camera_out(camera)
    if changed:
        await event_bus.publish("camera.status", out)
    return out


@router.get("/cameras/{camera_id}/playback", response_model=PlaybackInfo)
async def playback(camera_id: str, request: Request, db: AsyncSession = DB, user: User = Depends(any_user)):
    """Returns how to render the live view plus a short-lived, camera-scoped stream token.
    Source URLs with credentials are never exposed."""
    camera = await _get_camera(db, camera_id)
    if not camera.is_enabled:
        return PlaybackInfo(camera_id=camera_id, kind="unavailable", url=None, note="camera disabled")
    token, exp = create_stream_token(str(user.id), camera.id)
    # Players renew their token every few minutes; audit a viewing session, not every renewal
    recent = await db.scalar(
        select(AuditLog.id)
        .where(
            AuditLog.entity_type == "camera",
            AuditLog.entity_id == camera.id,
            AuditLog.action == "STREAM_ACCESSED",
            AuditLog.actor_id == str(user.id),
            AuditLog.created_at >= datetime.now(UTC) - timedelta(minutes=10),
        )
        .limit(1)
    )
    if recent is None:
        audit.record(db, user_actor(user, request), "STREAM_ACCESSED", "camera", camera.id)
        await db.commit()
    return get_adapter(camera.source_protocol).playback(camera, token, exp)


@router.get("/cameras/{camera_id}/snapshot", include_in_schema=True, responses={200: {"content": {"image/jpeg": {}}}})
async def snapshot(camera_id: str, token: str = Query(...), db: AsyncSession = DB):
    """Snapshot proxy for vendor-API cameras. Authorised by the stream token (img tags cannot send
    Authorization headers); the vendor API key never leaves the server."""
    try:
        payload = decode_token(token, "stream")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid stream token") from None
    if payload.get("cam") != camera_id:
        raise HTTPException(status_code=403, detail="Token not valid for this camera")
    camera = await _get_camera(db, camera_id)
    if camera.source_protocol != SourceProtocol.VENDOR_API:
        raise HTTPException(status_code=400, detail="Snapshots only for VENDOR_API cameras")
    adapter: VendorApiAdapter = get_adapter(SourceProtocol.VENDOR_API)  # type: ignore[assignment]
    try:
        r = await safe_get(
            camera.stream_endpoint.rstrip("/") + "/snapshot.jpg",
            timeout=get_settings().probe_timeout_s,
            headers=adapter.headers(camera),
        )
    except UnsafeTarget:
        raise HTTPException(status_code=400, detail="Camera endpoint is not allowed") from None
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Vendor API unreachable") from None
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Vendor API returned {r.status_code}")
    # Only relay images: the proxy must never become a channel to read arbitrary responses
    if not r.headers.get("content-type", "").startswith("image/") or len(r.content) > 5_000_000:
        raise HTTPException(status_code=502, detail="Vendor API did not return an image")
    return Response(content=r.content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/onvif/discover", response_model=list[OnvifDiscoveredDevice])
async def onvif_discover(
    body: OnvifDiscoverIn,
    db: AsyncSession = DB,
    _: User = Depends(admin_only),
):
    """Probe the configured ONVIF discovery targets (WS-Discovery multicast does not traverse
    container/VLAN boundaries, so production deployments run discovery on the edge gateway and
    report here)."""
    hosts = get_settings().onvif_host_list
    registered = set(
        (
            await db.execute(select(Camera.stream_endpoint).where(Camera.source_protocol == SourceProtocol.ONVIF))
        ).scalars()
    )

    async def probe(url: str) -> OnvifDiscoveredDevice | None:
        try:
            info = await get_device_information(url, body.username, body.password)
            uri = await get_stream_uri(url, body.username, body.password)
        except OnvifError as exc:
            log.info("onvif discovery %s failed: %s", url, exc)
            return None
        return OnvifDiscoveredDevice(
            device_service_url=url, stream_uri=uri, already_registered=url in registered, **info
        )

    found = await asyncio.gather(*(probe(h) for h in hosts))
    return [d for d in found if d]


@router.post("/internal/media-auth", include_in_schema=False)
async def media_auth(request: Request):
    """Auth hook called by the video gateway for every reader. Only reachable on the internal
    network (the edge proxy does not route /api/v1/internal)."""
    body = await request.json()
    s = get_settings()
    if body.get("action") == "api":
        # Control API: only the backend itself, identified by its shared secret
        ok = bool(s.gateway_api_secret) and hmac.compare_digest(
            f"{body.get('user')}:{body.get('password')}", f"{s.gateway_api_user}:{s.gateway_api_secret}"
        )
        if not ok:
            raise HTTPException(status_code=401)
        return {"ok": True}
    if body.get("action") not in ("read", "playback"):
        raise HTTPException(status_code=403)
    token = body.get("token") or ""
    if not token:
        token = (parse_qs(body.get("query") or "").get("token") or [""])[0]
    try:
        payload = decode_token(token, "stream")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401) from None
    if path_name(payload.get("cam", "")) != body.get("path"):
        raise HTTPException(status_code=403)
    return {"ok": True}
