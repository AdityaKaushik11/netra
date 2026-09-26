import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.update(
    DATABASE_URL=f"sqlite+aiosqlite:///{_db}",
    REDIS_URL="",
    GATEWAY_ENABLED="false",
    JWT_SECRET="test-secret-test-secret-test-secret-123",
    RATE_LIMIT_LOGIN_PER_MIN="1000",
    DEDUP_WINDOW_SECONDS="60",
)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import hash_api_key, hash_password  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ApiClient, Camera, User  # noqa: E402
from app.models.enums import CameraType, Role, SourceProtocol  # noqa: E402

API_KEY = "ntr_test_key_for_simulator_0123456789"
PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
async def database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        for name, role in [("admin", Role.ADMIN), ("operator", Role.OPERATOR), ("viewer", Role.VIEWER)]:
            db.add(User(username=name, full_name=name.title(), role=role, password_hash=hash_password(PASSWORD)))
        db.add(
            ApiClient(
                name="sim",
                key_prefix=API_KEY[:10],
                key_hash=hash_api_key(API_KEY),
                scopes=["events:write", "cameras:heartbeat", "cameras:write"],
            )
        )
        for cid, lat, lng in [("T001", 23.0120, 72.5626), ("T002", 23.0746, 72.5838), ("T003", 23.1365, 72.5436)]:
            db.add(
                Camera(
                    id=cid,
                    name=f"Test cam {cid}",
                    latitude=lat,
                    longitude=lng,
                    camera_type=CameraType.ANPR,
                    source_protocol=SourceProtocol.RTSP,
                    stream_endpoint=f"rtsp://camsim:8554/{cid.lower()}",
                )
            )
        await db.commit()
    yield
    await engine.dispose()


@pytest.fixture(scope="session")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _token(client, username):
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
async def admin(client):
    return await _token(client, "admin")


@pytest.fixture(scope="session")
async def operator(client):
    return await _token(client, "operator")


@pytest.fixture(scope="session")
async def viewer(client):
    return await _token(client, "viewer")


@pytest.fixture
def machine():
    return {"X-API-Key": API_KEY}
