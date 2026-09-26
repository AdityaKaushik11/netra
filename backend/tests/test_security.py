import pytest

from tests.conftest import PASSWORD


async def test_account_lockout_after_repeated_failures(client):
    for _ in range(5):
        r = await client.post("/api/v1/auth/login", json={"username": "ghost", "password": "nope"})
        assert r.status_code == 401
    r = await client.post("/api/v1/auth/login", json={"username": "ghost", "password": "nope"})
    assert r.status_code == 429 and "locked" in r.json()["detail"]


async def test_logout_revokes_token_server_side(client):
    r = await client.post("/api/v1/auth/login", json={"username": "viewer", "password": PASSWORD})
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200
    assert (await client.post("/api/v1/auth/logout", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_tampered_and_wrong_type_tokens_rejected(client, operator):
    token = operator["Authorization"].split()[1]
    forged = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})).status_code == 401
    # a camera stream token must not work as an API session
    play = (await client.get("/api/v1/cameras/T001/playback", headers=operator)).json()
    r = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {play['token']}"})
    assert r.status_code == 401


@pytest.mark.parametrize(
    "endpoint",
    [
        "rtsp://mysql:3306/x",
        "http://redis:6379/",
        "http://localhost:8000/api/v1/internal/media-auth",
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://metadata.google.internal/",
    ],
)
async def test_ssrf_endpoints_rejected(client, admin, endpoint):
    protocol = "RTSP" if endpoint.startswith("rtsp") else "HLS"
    body = {
        "id": "SSRF1",
        "name": "bad",
        "latitude": 23,
        "longitude": 72,
        "source_protocol": protocol,
        "stream_endpoint": endpoint,
    }
    r = await client.post("/api/v1/cameras", json=body, headers=admin)
    assert r.status_code == 422, r.text


async def test_private_camera_network_allowed(client, admin):
    body = {
        "id": "PRIV1",
        "name": "Private VLAN cam",
        "latitude": 23,
        "longitude": 72,
        "source_protocol": "RTSP",
        "stream_endpoint": "rtsp://192.168.10.20:554/stream1",
    }
    assert (await client.post("/api/v1/cameras", json=body, headers=admin)).status_code == 201


async def test_api_client_scopes_validated(client, admin):
    r = await client.post("/api/v1/api-clients", headers=admin, json={"name": "x-client", "scopes": ["admin:*"]})
    assert r.status_code == 422
    r = await client.post("/api/v1/api-clients", headers=admin, json={"name": "edge-1", "scopes": ["events:write"]})
    assert r.status_code == 201 and r.json()["api_key"].startswith("ntr_")


async def test_overlong_password_rejected(client, admin):
    body = {"username": "longpw", "full_name": "x", "password": "a" * 80, "role": "VIEWER"}
    assert (await client.post("/api/v1/users", json=body, headers=admin)).status_code == 422


async def test_security_headers_present(client):
    r = await client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
