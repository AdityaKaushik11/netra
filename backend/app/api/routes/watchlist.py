from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DB, any_user, operator_or_admin, user_actor
from app.models import Alert, DetectionEvent, User, WatchlistEntry
from app.models.enums import EntityType, WatchlistCategory
from app.schemas import Page
from app.schemas.alert import WatchlistCreate, WatchlistOut, WatchlistUpdate
from app.schemas.event import normalize_identifier
from app.services import audit, event_bus
from app.services.watchlist_matcher import matcher

router = APIRouter(tags=["watchlist"])


async def _enrich(db: AsyncSession, rows: list[WatchlistEntry]) -> list[WatchlistOut]:
    ids = [w.id for w in rows]
    norms = [w.identifier_normalized for w in rows]
    hits = (
        dict(
            (
                await db.execute(
                    select(Alert.watchlist_entry_id, func.count())
                    .where(Alert.watchlist_entry_id.in_(ids))
                    .group_by(Alert.watchlist_entry_id)
                )
            ).all()
        )
        if ids
        else {}
    )
    seen = (
        dict(
            (
                await db.execute(
                    select(DetectionEvent.identifier_normalized, func.max(DetectionEvent.detected_at))
                    .where(DetectionEvent.identifier_normalized.in_(norms))
                    .group_by(DetectionEvent.identifier_normalized)
                )
            ).all()
        )
        if norms
        else {}
    )
    out = []
    for w in rows:
        o = WatchlistOut.model_validate(w)
        o.hit_count = hits.get(w.id, 0)
        o.last_seen_at = seen.get(w.identifier_normalized)
        out.append(o)
    return out


@router.get("/watchlist", response_model=Page[WatchlistOut])
async def list_watchlist(
    q: str | None = Query(None, max_length=64),
    category: WatchlistCategory | None = None,
    entity_type: EntityType | None = None,
    active: bool | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = DB,
    _: User = Depends(any_user),
):
    stmt = select(WatchlistEntry)
    if q:
        norm = normalize_identifier(q) or q
        stmt = stmt.where(
            or_(WatchlistEntry.identifier_normalized.like(f"%{norm}%"), WatchlistEntry.description.ilike(f"%{q}%"))
        )
    if category:
        stmt = stmt.where(WatchlistEntry.category == category)
    if entity_type:
        stmt = stmt.where(WatchlistEntry.entity_type == entity_type)
    if active is not None:
        stmt = stmt.where(WatchlistEntry.is_active.is_(active))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        (await db.execute(stmt.order_by(WatchlistEntry.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    )
    return Page(items=await _enrich(db, list(rows)), total=total or 0, limit=limit, offset=offset)


@router.post("/watchlist", response_model=WatchlistOut, status_code=201)
async def create_entry(
    body: WatchlistCreate, request: Request, db: AsyncSession = DB, user: User = Depends(operator_or_admin)
):
    norm = normalize_identifier(body.identifier)
    if not norm:
        raise HTTPException(status_code=422, detail="Identifier must contain letters or digits")
    exists = await db.scalar(
        select(WatchlistEntry.id).where(
            WatchlistEntry.entity_type == body.entity_type, WatchlistEntry.identifier_normalized == norm
        )
    )
    if exists:
        raise HTTPException(status_code=409, detail="Entity already on watchlist")
    entry = WatchlistEntry(
        **body.model_dump(exclude={"identifier"}),
        identifier=body.identifier.strip().upper(),
        identifier_normalized=norm,
        created_by=user.id,
        is_active=True,
    )
    db.add(entry)
    await db.flush()
    audit.record(
        db,
        user_actor(user, request),
        "WATCHLIST_ADDED",
        "watchlist",
        entry.id,
        {"identifier": entry.identifier, "category": entry.category, "severity": entry.severity},
    )
    await db.commit()
    await matcher.invalidate()
    out = (await _enrich(db, [entry]))[0]
    await event_bus.publish("watchlist.changed", {"id": entry.id, "action": "added"})
    return out


@router.patch("/watchlist/{entry_id}", response_model=WatchlistOut)
async def update_entry(
    entry_id: int,
    body: WatchlistUpdate,
    request: Request,
    db: AsyncSession = DB,
    user: User = Depends(operator_or_admin),
):
    entry = await db.get(WatchlistEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(entry, k) for k in changes}
    for k, v in changes.items():
        setattr(entry, k, v)
    audit.record(db, user_actor(user, request), "WATCHLIST_UPDATED", "watchlist", entry.id, audit.diff(before, changes))
    await db.commit()
    await matcher.invalidate()
    await event_bus.publish("watchlist.changed", {"id": entry.id, "action": "updated"})
    return (await _enrich(db, [entry]))[0]


@router.delete("/watchlist/{entry_id}", response_model=WatchlistOut)
async def deactivate_entry(
    entry_id: int, request: Request, db: AsyncSession = DB, user: User = Depends(operator_or_admin)
):
    """Soft-delete: entries are deactivated, never erased, so past alerts stay explainable."""
    entry = await db.get(WatchlistEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Watchlist entry not found")
    entry.is_active = False
    audit.record(db, user_actor(user, request), "WATCHLIST_DEACTIVATED", "watchlist", entry.id)
    await db.commit()
    await matcher.invalidate()
    await event_bus.publish("watchlist.changed", {"id": entry.id, "action": "deactivated"})
    return (await _enrich(db, [entry]))[0]
