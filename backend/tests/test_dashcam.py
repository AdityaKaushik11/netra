from datetime import UTC, datetime

from app.services import dedup


async def test_dashcam_gps_telemetry_track_and_geolocated_events(client, admin, machine, operator):
    body = {
        "id": "D900",
        "name": "Test Dashcam",
        "latitude": 23.01,
        "longitude": 72.56,
        "camera_type": "DASHCAM",
        "source_protocol": "HLS",
        "stream_endpoint": "https://example.org/dash.m3u8",
        "health_mode": "HEARTBEAT",
    }
    assert (await client.post("/api/v1/cameras", json=body, headers=admin)).status_code == 201

    for lat, lng, speed in [(23.020, 72.570, 32.0), (23.030, 72.569, 41.5)]:
        r = await client.post(
            "/api/v1/cameras/D900/heartbeat",
            headers=machine,
            json={"latitude": lat, "longitude": lng, "speed_kmh": speed, "heading_deg": 350, "fps": 15},
        )
        assert r.status_code == 202
    cam = (await client.get("/api/v1/cameras/D900", headers=admin)).json()
    assert (cam["latitude"], cam["longitude"], cam["speed_kmh"]) == (23.03, 72.569, 41.5)
    assert cam["status"] == "ONLINE" and "latitude" not in (cam["health_metrics"] or {})
    track = (await client.get("/api/v1/cameras/D900/track?minutes=5", headers=admin)).json()
    assert [p["latitude"] for p in track] == [23.02, 23.03]

    # The event carries the capture position; the alert is geolocated where the van was
    await client.post(
        "/api/v1/watchlist",
        headers=operator,
        json={"identifier": "GJ01DC0001", "category": "STOLEN_VEHICLE", "severity": "HIGH"},
    )
    dedup.reset_local()
    r = await client.post(
        "/api/v1/events",
        headers=machine,
        json={
            "camera_id": "D900",
            "event_type": "ANPR",
            "timestamp": datetime.now(UTC).isoformat(),
            "vehicle_number": "GJ01DC0001",
            "confidence": 0.9,
            "latitude": 23.041,
            "longitude": 72.545,
            "speed_kmh": 38,
        },
    )
    assert r.status_code == 201 and r.json()["alert_ids"]
    alert = (await client.get(f"/api/v1/alerts/{r.json()['alert_ids'][0]}", headers=operator)).json()
    assert (alert["latitude"], alert["longitude"]) == (23.041, 72.545)

    # ADAS events are stored without identity
    r = await client.post(
        "/api/v1/events",
        headers=machine,
        json={
            "camera_id": "D900",
            "event_type": "OVERSPEED",
            "timestamp": datetime.now(UTC).isoformat(),
            "confidence": 0.92,
            "object_label": "68 km/h in 50 zone",
            "latitude": 23.04,
            "longitude": 72.54,
        },
    )
    assert r.status_code == 201


async def test_half_gps_fix_rejected(client, machine):
    r = await client.post(
        "/api/v1/events",
        headers=machine,
        json={
            "camera_id": "T001",
            "event_type": "OVERSPEED",
            "timestamp": datetime.now(UTC).isoformat(),
            "confidence": 0.9,
            "latitude": 23.0,
        },
    )
    assert r.status_code == 422


async def test_clip_requires_recordable_camera(client, admin):
    # HLS camera from the test above has no gateway recording
    r = await client.get("/api/v1/cameras/D900/clip", headers=admin)
    assert r.status_code == 400
