async def test_login_rejects_bad_password(client):
    r = await client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


async def test_requires_auth(client):
    assert (await client.get("/api/v1/cameras")).status_code == 401


async def test_admin_onboards_camera_and_credentials_are_hidden(client, admin):
    body = {
        "id": "C900",
        "name": "Test Junction",
        "latitude": 23.03,
        "longitude": 72.58,
        "camera_type": "ANPR",
        "source_protocol": "RTSP",
        "stream_endpoint": "rtsp://10.0.0.5:554/stream1",
        "stream_username": "svc",
        "stream_password": "s3cret-pass",
        "zone": "Test Zone",
    }
    r = await client.post("/api/v1/cameras", json=body, headers=admin)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["has_credentials"] is True
    assert data["onboarding_source"] == "MANUAL"
    assert "s3cret-pass" not in r.text and "stream_password" not in data

    r = await client.get("/api/v1/cameras", params={"q": "Test Junction"}, headers=admin)
    assert r.json()["total"] == 1

    r = await client.get("/api/v1/cameras/C900/audit", headers=admin)
    assert "CAMERA_ONBOARDED" in [a["action"] for a in r.json()]


async def test_inline_credentials_rejected(client, admin):
    body = {
        "id": "C901",
        "name": "Bad",
        "latitude": 23,
        "longitude": 72,
        "source_protocol": "RTSP",
        "stream_endpoint": "rtsp://user:pass@10.0.0.5/stream",
    }
    r = await client.post("/api/v1/cameras", json=body, headers=admin)
    assert r.status_code == 422


async def test_protocol_scheme_validation(client, admin):
    body = {
        "id": "C902",
        "name": "Bad",
        "latitude": 23,
        "longitude": 72,
        "source_protocol": "HLS",
        "stream_endpoint": "rtsp://10.0.0.5/stream",
    }
    assert (await client.post("/api/v1/cameras", json=body, headers=admin)).status_code == 422


async def test_api_key_onboarding(client, machine):
    body = {
        "cameras": [
            {
                "id": "C910",
                "name": "Bulk A",
                "latitude": 23.1,
                "longitude": 72.6,
                "source_protocol": "HLS",
                "stream_endpoint": "https://example.org/a.m3u8",
            },
            {
                "id": "C910",
                "name": "Dup",
                "latitude": 23.1,
                "longitude": 72.6,
                "source_protocol": "HLS",
                "stream_endpoint": "https://example.org/b.m3u8",
            },
        ]
    }
    r = await client.post("/api/v1/cameras/bulk", json=body, headers=machine)
    assert r.status_code == 200, r.text
    assert r.json()["created"] == ["C910"]
    assert "C910" in r.json()["errors"]


async def test_viewer_cannot_modify(client, viewer):
    r = await client.patch("/api/v1/cameras/T001", json={"name": "hack"}, headers=viewer)
    assert r.status_code == 403


async def test_disable_is_audited(client, admin):
    r = await client.patch("/api/v1/cameras/C900", json={"is_enabled": False}, headers=admin)
    assert r.status_code == 200
    assert r.json()["status"] == "OFFLINE"
    audit = (await client.get("/api/v1/cameras/C900/audit", headers=admin)).json()
    assert audit[0]["action"] == "CAMERA_DISABLED"


async def test_playback_issues_scoped_token(client, operator):
    r = await client.get("/api/v1/cameras/T001/playback", headers=operator)
    assert r.status_code == 200
    info = r.json()
    assert info["kind"] == "hls" and info["token"]
    assert "rtsp://" not in r.text
    ok = await client.post(
        "/api/v1/internal/media-auth", json={"action": "read", "path": "cam-t001", "query": f"token={info['token']}"}
    )
    assert ok.status_code == 200
    denied = await client.post(
        "/api/v1/internal/media-auth", json={"action": "read", "path": "cam-t002", "query": f"token={info['token']}"}
    )
    assert denied.status_code == 403
