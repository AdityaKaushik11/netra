from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, any_user, operator_or_admin, user_actor
from app.models import Alert, User
from app.models.enums import AlertStatus, Severity
from app.schemas import Page
from app.schemas.alert import AlertAction, AlertBulkAction, AlertBulkResult, AlertOut, AlertResolve
from app.schemas.event import normalize_identifier
from app.services import audit, event_bus
from app.services.serializers import alert_out

router = APIRouter(tags=["alerts"])


@router.get("/alerts", response_model=Page[AlertOut])
async def list_alerts(
    status: list[AlertStatus] | None = Query(None),
    severity: list[Severity] | None = Query(None),
    camera_id: str | None = None,
    identifier: str | None = None,
    since: datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = DB,
    _: User = Depends(any_user),
):
    stmt = select(Alert)
    if status:
        stmt = stmt.where(Alert.status.in_(status))
    if severity:
        stmt = stmt.where(Alert.severity.in_(severity))
    if camera_id:
        stmt = stmt.where(Alert.camera_id == camera_id)
    if identifier:
        stmt = stmt.where(Alert.identifier_normalized == normalize_identifier(identifier))
    if since:
        stmt = stmt.where(Alert.triggered_at >= since)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(Alert.triggered_at.desc()).limit(limit).offset(offset))).scalars()
    return Page(items=[alert_out(a) for a in rows], total=total or 0, limit=limit, offset=offset)


@router.post("/alerts/bulk", response_model=AlertBulkResult)
async def bulk_action(
    body: AlertBulkAction,
    request: Request,
    db: AsyncSession = DB,
    user: User = Depends(operator_or_admin),
):
    """Acknowledge or resolve many alerts at once (by ids, or all open alerts older than N minutes).
    Every change is audited individually."""
    if not body.ids and not body.older_than_minutes:
        raise HTTPException(status_code=422, detail="Provide ids or older_than_minutes")
    if body.action == "resolve" and (not body.note or len(body.note.strip()) < 3):
        raise HTTPException(status_code=422, detail="A resolution note is required")
    stmt = select(Alert).where(Alert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED]))
    if body.ids:
        stmt = stmt.where(Alert.id.in_(body.ids))
    if body.older_than_minutes:
        stmt = stmt.where(Alert.last_hit_at < datetime.now(UTC) - timedelta(minutes=body.older_than_minutes))
    if body.action == "acknowledge":
        stmt = stmt.where(Alert.status == AlertStatus.NEW)
    alerts = list((await db.execute(stmt.limit(5000))).scalars())
    now = datetime.now(UTC)
    actor = user_actor(user, request)
    for a in alerts:
        if a.acknowledged_at is None:
            a.acknowledged_by, a.acknowledged_at = user.id, now
        if body.action == "acknowledge":
            a.status = AlertStatus.ACKNOWLEDGED
            audit.record(db, actor, "ALERT_ACKNOWLEDGED", "alert", a.id, {"note": body.note, "bulk": True})
        else:
            a.status = AlertStatus.FALSE_POSITIVE if body.false_positive else AlertStatus.RESOLVED
            a.resolved_by, a.resolved_at, a.resolution_note = user.id, now, body.note
            audit.record(db, actor, "ALERT_RESOLVED", "alert", a.id, {"note": body.note, "bulk": True})
    await db.commit()
    if alerts:
        await event_bus.publish("alert.updated", {"bulk": len(alerts)})
    return AlertBulkResult(updated=len(alerts))


async def _get(db: AsyncSession, alert_id: int) -> Alert:
    alert = await db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.get("/alerts/{alert_id}", response_model=AlertOut)
async def get_alert(alert_id: int, db: AsyncSession = DB, _: User = Depends(any_user)):
    return alert_out(await _get(db, alert_id))


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge(
    alert_id: int,
    body: AlertAction,
    request: Request,
    db: AsyncSession = DB,
    user: User = Depends(operator_or_admin),
):
    alert = await _get(db, alert_id)
    if alert.status != AlertStatus.NEW:
        raise HTTPException(status_code=409, detail=f"Alert is already {alert.status}")
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = user.id
    alert.acknowledged_at = datetime.now(UTC)
    if body.note:
        alert.resolution_note = body.note
    audit.record(db, user_actor(user, request), "ALERT_ACKNOWLEDGED", "alert", alert.id, {"note": body.note})
    await db.commit()
    out = alert_out(alert)
    await event_bus.publish("alert.updated", out)
    return out


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
async def resolve(
    alert_id: int,
    body: AlertResolve,
    request: Request,
    db: AsyncSession = DB,
    user: User = Depends(operator_or_admin),
):
    alert = await _get(db, alert_id)
    if alert.status in (AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE):
        raise HTTPException(status_code=409, detail="Alert already closed")
    now = datetime.now(UTC)
    if alert.acknowledged_at is None:
        alert.acknowledged_by, alert.acknowledged_at = user.id, now
    alert.status = AlertStatus.FALSE_POSITIVE if body.false_positive else AlertStatus.RESOLVED
    alert.resolved_by = user.id
    alert.resolved_at = now
    alert.resolution_note = body.note
    audit.record(
        db,
        user_actor(user, request),
        "ALERT_RESOLVED",
        "alert",
        alert.id,
        {"note": body.note, "false_positive": body.false_positive},
    )
    await db.commit()
    out = alert_out(alert)
    await event_bus.publish("alert.updated", out)
    return out
