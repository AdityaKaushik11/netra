from datetime import UTC, datetime, timedelta

import pytest

from app.services import dedup


def ev(camera="T001", plate="GJ01AB1234", minutes_ago=0, **kw):
    return {
        "camera_id": camera,
        "event_type": "ANPR",
        "timestamp": (datetime.now(UTC) - timedelta(minutes=minutes_ago)).isoformat(),
        "vehicle_number": plate,
        "confidence": 0.93,
        "vehicle_type": "car",
        "bounding_box": {"x": 10, "y": 20, "w": 100, "h": 40},
        **kw,
    }


@pytest.fixture(autouse=True)
def clear_dedup():
    dedup.reset_local()


async def test_validation_errors(client, machine):
    assert (await client.post("/api/v1/events", json=ev(camera="NOPE"), headers=machine)).status_code == 404
    bad = ev()
    bad["confidence"] = 1.7
    assert (await client.post("/api/v1/events", json=bad, headers=machine)).status_code == 422
    naive = ev()
    naive["timestamp"] = "2026-01-01T10:00:00"
    assert (await client.post("/api/v1/events", json=naive, headers=machine)).status_code == 422
    future = ev(minutes_ago=-60)
    assert (await client.post("/api/v1/events", json=future, headers=machine)).status_code == 422


async def test_idempotent_retry(client, machine):
    body = ev(plate="GJ01ZZ0001", event_id="edge-42-0001")
    first = await client.post("/api/v1/events", json=body, headers=machine)
    second = await client.post("/api/v1/events", json=body, headers=machine)
    assert first.status_code == 201 and second.status_code == 200
    assert second.json()["status"] == "duplicate"
    assert first.json()["event_id"] == second.json()["event_id"]


async def test_repeat_reads_are_suppressed(client, machine, admin):
    first = await client.post("/api/v1/events", json=ev(plate="GJ01ZZ0002"), headers=machine)
    assert first.json()["status"] == "created"
    for _ in range(3):
        r = await client.post("/api/v1/events", json=ev(plate="GJ 01 ZZ 0002"), headers=machine)
        assert r.json()["status"] == "suppressed"
    event = (await client.get(f"/api/v1/events/{first.json()['event_id']}", headers=admin)).json()
    assert event["repeat_count"] == 3
    # A different camera is a new sighting, not a duplicate
    other = await client.post("/api/v1/events", json=ev(camera="T002", plate="GJ01ZZ0002"), headers=machine)
    assert other.json()["status"] == "created"


async def test_watchlist_match_raises_alert_with_cooldown(client, machine, operator):
    r = await client.post(
        "/api/v1/watchlist",
        headers=operator,
        json={"identifier": "GJ01XX0001", "category": "STOLEN_VEHICLE", "severity": "CRITICAL", "description": "test"},
    )
    assert r.status_code == 201, r.text

    r = await client.post("/api/v1/events", json=ev(plate="GJ01XX0001"), headers=machine)
    assert r.json()["status"] == "created" and len(r.json()["alert_ids"]) == 1
    alert_id = r.json()["alert_ids"][0]
    alert = (await client.get(f"/api/v1/alerts/{alert_id}", headers=operator)).json()
    assert alert["severity"] == "CRITICAL" and alert["match_type"] == "EXACT" and alert["status"] == "NEW"
    assert alert["camera_id"] == "T001" and alert["latitude"] == pytest.approx(23.012)

    # Past the dedup window, a new read at the same camera updates the open alert instead of a new one
    dedup.reset_local()
    r2 = await client.post("/api/v1/events", json=ev(plate="GJ01XX0001"), headers=machine)
    assert r2.json()["alert_ids"] == [alert_id]
    assert (await client.get(f"/api/v1/alerts/{alert_id}", headers=operator)).json()["hit_count"] == 2


async def test_fuzzy_match_downgrades_severity(client, machine, operator):
    await client.post(
        "/api/v1/watchlist",
        headers=operator,
        json={"identifier": "GJ05XX1234", "category": "STOLEN_VEHICLE", "severity": "HIGH"},
    )
    r = await client.post("/api/v1/events", json=ev(camera="T002", plate="GJ05XX1Z34"), headers=machine)
    alert = (await client.get(f"/api/v1/alerts/{r.json()['alert_ids'][0]}", headers=operator)).json()
    assert alert["match_type"] == "FUZZY" and alert["severity"] == "MEDIUM"


async def test_low_confidence_does_not_alert(client, machine):
    r = await client.post("/api/v1/events", json=ev(camera="T003", plate="GJ01XX0001", confidence=0.3), headers=machine)
    assert r.json()["status"] == "created" and r.json()["alert_ids"] == []


async def test_alert_workflow(client, machine, operator, viewer):
    await client.post(
        "/api/v1/watchlist",
        headers=operator,
        json={"identifier": "GJ27XX7788", "category": "BLACKLISTED_VEHICLE", "severity": "HIGH"},
    )
    r = await client.post("/api/v1/events", json=ev(camera="T003", plate="GJ27XX7788"), headers=machine)
    aid = r.json()["alert_ids"][0]
    assert (await client.post(f"/api/v1/alerts/{aid}/acknowledge", json={}, headers=viewer)).status_code == 403
    r = await client.post(f"/api/v1/alerts/{aid}/acknowledge", json={"note": "dispatching"}, headers=operator)
    assert r.json()["status"] == "ACKNOWLEDGED"
    assert (await client.post(f"/api/v1/alerts/{aid}/acknowledge", json={}, headers=operator)).status_code == 409
    r = await client.post(f"/api/v1/alerts/{aid}/resolve", json={"note": "intercepted"}, headers=operator)
    assert r.json()["status"] == "RESOLVED" and r.json()["resolved_at"]


async def test_trace_orders_stops_and_flags_impossible_travel(client, machine, admin):
    plate = "GJ01TR0001"
    for cam, mins in [("T003", 5), ("T001", 60), ("T002", 40)]:
        await client.post("/api/v1/events", json=ev(camera=cam, plate=plate, minutes_ago=mins), headers=machine)
    r = await client.get(f"/api/v1/trace/{plate}", headers=admin)
    data = r.json()
    assert [s["camera_id"] for s in data["stops"]] == ["T001", "T002", "T003"]
    assert data["distinct_cameras"] == 3 and data["total_distance_km"] > 5
    assert data["anomalies"] == []

    # Two sightings 15 km apart one minute apart -> cloned plate anomaly
    await client.post("/api/v1/events", json=ev(camera="T001", plate="GJ01CL0001", minutes_ago=2), headers=machine)
    await client.post("/api/v1/events", json=ev(camera="T003", plate="GJ01CL0001", minutes_ago=1), headers=machine)
    data = (await client.get("/api/v1/trace/GJ01CL0001", headers=admin)).json()
    assert data["anomalies"] and "Impossible travel" in data["anomalies"][0]


async def test_batch_and_stats(client, machine, admin):
    r = await client.post(
        "/api/v1/events/batch",
        headers=machine,
        json={"events": [ev(plate="GJ01BA0001"), ev(plate="GJ01BA0001"), ev(camera="MISSING", plate="GJ01BA0002")]},
    )
    body = r.json()
    assert (body["created"], body["suppressed"], body["rejected"]) == (1, 1, 1)
    stats = (await client.get("/api/v1/stats/overview", headers=admin)).json()
    assert stats["events"]["last_hour"] > 0 and stats["alerts"]["open"] >= 1
    series = (await client.get("/api/v1/stats/timeseries?hours=6", headers=admin)).json()
    assert len(series) == 6 and sum(p["detections"] for p in series) > 0
    search = (await client.get("/api/v1/search", params={"q": "GJ01XX"}, headers=admin)).json()
    assert any(e["identifier_normalized"] == "GJ01XX0001" for e in search["entities"])


async def test_bulk_resolve(client, machine, operator, viewer):
    await client.post(
        "/api/v1/watchlist",
        headers=operator,
        json={"identifier": "GJ01BK0001", "category": "SUSPICIOUS", "severity": "LOW"},
    )
    ids = []
    for cam in ("T001", "T002"):
        r = await client.post("/api/v1/events", json=ev(camera=cam, plate="GJ01BK0001"), headers=machine)
        ids += r.json()["alert_ids"]
    body = {"action": "resolve", "ids": ids, "note": "patrol cleared"}
    assert (await client.post("/api/v1/alerts/bulk", json=body, headers=viewer)).status_code == 403
    assert (await client.post("/api/v1/alerts/bulk", json={**body, "note": ""}, headers=operator)).status_code == 422
    r = await client.post("/api/v1/alerts/bulk", json=body, headers=operator)
    assert r.json()["updated"] == 2
    for i in ids:
        assert (await client.get(f"/api/v1/alerts/{i}", headers=operator)).json()["status"] == "RESOLVED"
