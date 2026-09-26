from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Alert, DetectionEvent
from app.models.enums import AlertStatus, EventType, MatchType, Severity
from app.services.health_monitor import prune_old_data


async def test_retention_prunes_old_events_but_keeps_alert_evidence(client, operator):
    old = datetime.now(UTC) - timedelta(days=45)
    await client.post(
        "/api/v1/watchlist",
        headers=operator,
        json={"identifier": "GJ01RT0001", "category": "SUSPICIOUS", "severity": "LOW"},
    )
    async with SessionLocal() as db:
        stale = DetectionEvent(
            event_uid="ret-stale",
            camera_id="T001",
            event_type=EventType.ANPR,
            detected_at=old,
            received_at=old,
            identifier="GJ01RT0002",
            identifier_normalized="GJ01RT0002",
            confidence=0.9,
            latitude=23.0,
            longitude=72.5,
            repeat_count=0,
        )
        evidence = DetectionEvent(
            event_uid="ret-evidence",
            camera_id="T001",
            event_type=EventType.ANPR,
            detected_at=old,
            received_at=old,
            identifier="GJ01RT0001",
            identifier_normalized="GJ01RT0001",
            confidence=0.9,
            latitude=23.0,
            longitude=72.5,
            repeat_count=0,
            watchlist_hit=True,
        )
        db.add_all([stale, evidence])
        await db.flush()
        from app.models import WatchlistEntry

        entry = await db.scalar(select(WatchlistEntry).where(WatchlistEntry.identifier_normalized == "GJ01RT0001"))
        db.add(
            Alert(
                event_id=evidence.id,
                watchlist_entry_id=entry.id,
                camera_id="T001",
                identifier="GJ01RT0001",
                identifier_normalized="GJ01RT0001",
                match_type=MatchType.EXACT,
                confidence=0.9,
                severity=Severity.LOW,
                status=AlertStatus.RESOLVED,
                title="t",
                latitude=23.0,
                longitude=72.5,
                triggered_at=old,
                last_hit_at=old,
            )
        )
        await db.commit()

    await prune_old_data()

    async with SessionLocal() as db:
        uids = set((await db.execute(select(DetectionEvent.event_uid))).scalars())
    assert "ret-stale" not in uids
    assert "ret-evidence" in uids
