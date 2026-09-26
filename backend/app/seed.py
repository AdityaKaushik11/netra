"""Idempotent bootstrap: departments, users, API client, demo cameras, synthetic watchlist and a
day of background detection history so the dashboard is meaningful on first launch.

Run: python -m app.seed   (passwords / keys come from the environment, never from code)
"""

import asyncio
import json
import logging
import os
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import encrypt_secret, hash_api_key, hash_password
from app.db import SessionLocal, engine
from app.models import Alert, ApiClient, Camera, Department, DetectionEvent, User, WatchlistEntry
from app.models.enums import (
    AlertStatus,
    CameraStatus,
    CameraType,
    HealthMode,
    MatchType,
    OnboardingSource,
    Role,
    SourceProtocol,
)
from app.schemas.event import normalize_identifier

log = logging.getLogger("seed")
DATA = Path(__file__).parent / "seed_data"

DEPARTMENTS = [
    ("AHM-TRF", "Ahmedabad Traffic Police"),
    ("AHM-CITY", "Ahmedabad City Police"),
    ("RTO-GJ", "Regional Transport Office, Gujarat"),
    ("GNR-POL", "Gandhinagar Police"),
]


def demo_cameras() -> list[dict]:
    camsim = os.getenv("CAMSIM_HOST", "camsim")
    sim = os.getenv("SIMULATOR_HOST", "simulator")
    cam_user = os.getenv("CAMSIM_USER", "viewer")
    cam_pass = os.getenv("CAMSIM_PASSWORD", "")
    public_hls = os.getenv("PUBLIC_HLS_URL", "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8")
    return [
        dict(
            id="C001",
            name="Paldi Cross Roads Junction",
            dept="AHM-TRF",
            zone="Ahmedabad West",
            address="Paldi Char Rasta, Ahmedabad",
            latitude=23.012030,
            longitude=72.562610,
            camera_type=CameraType.ANPR,
            source_protocol=SourceProtocol.RTSP,
            stream_endpoint=f"rtsp://{camsim}:8554/c001",
            stream_username=cam_user,
            password=cam_pass,
            vendor="Hikvision (simulated)",
            model="DS-2CD7A26G0",
            resolution="1280x720",
            fps=15,
            recording_enabled=True,
            storage_tier="HOT",
            storage_location="s3://netra-hot/ahm-west/C001",
        ),
        dict(
            id="C002",
            name="Subhash Bridge RTO Checkpoint",
            dept="RTO-GJ",
            zone="Ahmedabad North",
            address="RTO Circle, Subhash Bridge, Ahmedabad",
            latitude=23.074620,
            longitude=72.583840,
            camera_type=CameraType.ANPR,
            source_protocol=SourceProtocol.RTSP,
            stream_endpoint=f"rtsp://{camsim}:8554/c002",
            stream_username=cam_user,
            password=cam_pass,
            vendor="CP Plus (simulated)",
            model="CP-VNC-T41ZL5",
            resolution="1280x720",
            fps=15,
            recording_enabled=True,
            storage_tier="HOT",
            storage_location="s3://netra-hot/ahm-north/C002",
        ),
        dict(
            id="C003",
            name="ISKCON Cross Roads, SG Highway",
            dept="AHM-CITY",
            zone="Ahmedabad West",
            address="ISKCON Cross Rd, SG Highway, Ahmedabad",
            latitude=23.025790,
            longitude=72.507320,
            camera_type=CameraType.PTZ,
            source_protocol=SourceProtocol.ONVIF,
            stream_endpoint=f"http://{sim}:8081/onvif/device_service",
            stream_username=os.getenv("ONVIF_USER", "admin"),
            password=os.getenv("ONVIF_PASSWORD", ""),
            vendor="ONVIF Profile S (mock)",
            model="NetraSim PTZ-1",
            resolution="1280x720",
            fps=15,
            recording_enabled=True,
            storage_tier="WARM",
            storage_location="nfs://nvr-ahm-west/C003",
        ),
        dict(
            id="C004",
            name="Kalupur Railway Station Approach",
            dept="AHM-CITY",
            zone="Ahmedabad East",
            address="Kalupur, Ahmedabad",
            latitude=23.026880,
            longitude=72.600810,
            camera_type=CameraType.DOME,
            source_protocol=SourceProtocol.HLS,
            stream_endpoint=public_hls,
            vendor="Existing city VMS (HLS)",
            resolution="1280x720",
            fps=24,
            recording_enabled=False,
            storage_tier="WARM",
            storage_location="external-vms",
        ),
        dict(
            id="C005",
            name="Vaishnodevi Circle, SG Highway Toll",
            dept="AHM-TRF",
            zone="Ahmedabad North",
            address="Vaishnodevi Circle, S.G. Highway",
            latitude=23.136480,
            longitude=72.543610,
            camera_type=CameraType.BULLET,
            source_protocol=SourceProtocol.VENDOR_API,
            stream_endpoint=f"http://{sim}:8090/vendor/api/v1/channels/1",
            password=os.getenv("VENDOR_API_KEY", ""),
            vendor="Vendor NVR cloud (simulated)",
            model="NVR-X16",
            resolution="1920x1080",
            fps=10,
            recording_enabled=True,
            storage_tier="HOT",
            storage_location="vendor-cloud://nvr-x16/ch1",
        ),
        dict(
            id="C006",
            name="CH-0 Circle, Gandhinagar",
            dept="GNR-POL",
            zone="Gandhinagar",
            address="CH-0 Circle, Gandhinagar",
            latitude=23.215630,
            longitude=72.636940,
            camera_type=CameraType.ANPR,
            source_protocol=SourceProtocol.RTSP,
            stream_endpoint=f"rtsp://{camsim}:8554/c006",
            stream_username=cam_user,
            password=cam_pass,
            vendor="Dahua (simulated)",
            model="ITC237-PW6M",
            resolution="1280x720",
            fps=15,
            recording_enabled=True,
            storage_tier="HOT",
            storage_location="s3://netra-hot/gnr/C006",
            health_mode=HealthMode.HEARTBEAT,
        ),
        # Mobile source: vehicle-mounted dashcam on a patrol van, streaming video over 4G and
        # reporting GPS telemetry + on-device ANPR / ADAS events (okDriver-style dashcam)
        dict(
            id="D001",
            name="PCR Van 12 · okDriver Dashcam",
            dept="AHM-CITY",
            zone="Mobile patrol",
            address="Vehicle GJ01GP0012 (patrol route, Ahmedabad West)",
            latitude=23.012030,
            longitude=72.562610,
            camera_type=CameraType.DASHCAM,
            source_protocol=SourceProtocol.RTSP,
            stream_endpoint=f"rtsp://{camsim}:8554/d001",
            stream_username=cam_user,
            password=cam_pass,
            vendor="okDriver (simulated)",
            model="Smart Dashcam 4G",
            resolution="1280x720",
            fps=15,
            recording_enabled=True,
            storage_tier="HOT",
            storage_location="edge-sd://D001 + s3://netra-hot/mobile/D001",
            retention_days=15,
            health_mode=HealthMode.HEARTBEAT,
        ),
    ]


STATES = ["GJ01", "GJ01", "GJ01", "GJ18", "GJ27", "GJ05", "GJ06", "GJ38", "MH12", "RJ14"]
VEHICLE_TYPES = ["car", "car", "car", "motorcycle", "motorcycle", "auto_rickshaw", "truck", "bus", "suv"]
COLORS = ["white", "silver", "black", "grey", "red", "blue"]


def random_plate(rng: random.Random) -> str:
    letters = "ABCDEFGHJKLMNPRSTUVWZ"
    return f"{rng.choice(STATES)}{rng.choice(letters)}{rng.choice(letters)}{rng.randint(1, 9999):04d}"


async def seed() -> None:
    s = get_settings()
    rng = random.Random(42)
    async with SessionLocal() as db:
        # Departments
        depts = {d.code: d for d in (await db.execute(select(Department))).scalars()}
        for code, name in DEPARTMENTS:
            if code not in depts:
                depts[code] = Department(code=code, name=name)
                db.add(depts[code])
        await db.flush()

        # Users
        for username, full_name, role, pwd in [
            (s.admin_username, "Platform Administrator", Role.ADMIN, s.admin_password),
            ("operator", "Control Room Operator", Role.OPERATOR, s.operator_password),
            ("viewer", "Read-only Analyst", Role.VIEWER, s.viewer_password),
        ]:
            if not pwd:
                log.warning("password for %s not set in environment; user not created", username)
                continue
            if not await db.scalar(select(User.id).where(User.username == username)):
                db.add(
                    User(
                        username=username,
                        full_name=full_name,
                        role=role,
                        password_hash=hash_password(pwd),
                        department_id=depts["AHM-CITY"].id,
                    )
                )

        # Machine client for the simulators
        if s.seed_api_key and not await db.scalar(select(ApiClient.id).where(ApiClient.name == "analytics-simulator")):
            db.add(
                ApiClient(
                    name="analytics-simulator",
                    key_prefix=s.seed_api_key[:10],
                    key_hash=hash_api_key(s.seed_api_key),
                    scopes=["events:write", "cameras:heartbeat", "cameras:write"],
                )
            )

        # Cameras
        for c in demo_cameras():
            if await db.get(Camera, c["id"]):
                continue
            dept = depts[c.pop("dept")]
            password = c.pop("password", None)
            db.add(
                Camera(
                    **c,
                    department_id=dept.id,
                    stream_secret_enc=encrypt_secret(password),
                    status=CameraStatus.UNKNOWN,
                    onboarding_source=OnboardingSource.SEED,
                    is_enabled=True,
                    tags=["demo"],
                )
            )
        await db.flush()

        # Watchlist
        data = json.loads((DATA / "watchlist.json").read_text())
        for e in data["entries"]:
            norm = normalize_identifier(e["identifier"])
            exists = await db.scalar(select(WatchlistEntry.id).where(WatchlistEntry.identifier_normalized == norm))
            if not exists:
                db.add(WatchlistEntry(**e, identifier_normalized=norm, is_active=True))
        await db.commit()

        # Background history (only on an empty database)
        if (await db.scalar(select(func.count()).select_from(DetectionEvent))) == 0:
            await _seed_history(db, rng)
    await engine.dispose()
    log.info("seed complete")


async def _seed_history(db, rng: random.Random) -> None:
    cameras = list((await db.execute(select(Camera))).scalars())
    anpr_cams = [c for c in cameras if c.camera_type in (CameraType.ANPR, CameraType.BULLET, CameraType.PTZ)]
    watch = {w.identifier_normalized: w for w in (await db.execute(select(WatchlistEntry))).scalars()}
    now = datetime.now(UTC)
    fleet = [random_plate(rng) for _ in range(160)]
    for _ in range(420):
        cam = rng.choice(anpr_cams)
        # traffic follows a daily curve: more events in daytime hours
        t = now - timedelta(minutes=rng.triangular(10, 24 * 60, 8 * 60))
        plate = rng.choice(fleet)
        db.add(
            DetectionEvent(
                event_uid=f"seed-{uuid.uuid4().hex}",
                camera_id=cam.id,
                event_type="ANPR",
                detected_at=t,
                received_at=t + timedelta(milliseconds=rng.randint(80, 900)),
                identifier=plate,
                identifier_normalized=plate,
                vehicle_type=rng.choice(VEHICLE_TYPES),
                vehicle_color=rng.choice(COLORS),
                confidence=round(rng.uniform(0.72, 0.99), 3),
                bounding_box={"x": rng.randint(200, 900), "y": rng.randint(300, 600), "w": 180, "h": 48},
                model_name="anpr-yolov8n+paddleocr (simulated)",
                source_client="seed",
                latitude=cam.latitude,
                longitude=cam.longitude,
                repeat_count=rng.choice([0, 0, 1, 2, 3, 5]),
            )
        )
    # A few historical, already-handled watchlist hits
    for plate, status, hours_ago in [
        ("GJ18XX4321", AlertStatus.RESOLVED, 20),
        ("GJ06XX8080", AlertStatus.RESOLVED, 14),
        ("RJ14XX3030", AlertStatus.ACKNOWLEDGED, 5),
        ("MH12XX9090", AlertStatus.RESOLVED, 9),
    ]:
        cam = rng.choice(anpr_cams)
        t = now - timedelta(hours=hours_ago, minutes=rng.randint(0, 50))
        entry = watch[plate]
        ev = DetectionEvent(
            event_uid=f"seed-{uuid.uuid4().hex}",
            camera_id=cam.id,
            event_type="ANPR",
            detected_at=t,
            received_at=t,
            identifier=plate,
            identifier_normalized=plate,
            vehicle_type="car",
            confidence=0.93,
            model_name="anpr-yolov8n+paddleocr (simulated)",
            source_client="seed",
            latitude=cam.latitude,
            longitude=cam.longitude,
            repeat_count=2,
            watchlist_hit=True,
        )
        db.add(ev)
        await db.flush()
        db.add(
            Alert(
                event_id=ev.id,
                watchlist_entry_id=entry.id,
                camera_id=cam.id,
                identifier=plate,
                identifier_normalized=plate,
                match_type=MatchType.EXACT,
                confidence=0.93,
                severity=entry.severity,
                status=status,
                title=f"Watchlist match {plate} at {cam.name}",
                latitude=cam.latitude,
                longitude=cam.longitude,
                triggered_at=t,
                last_hit_at=t,
                hit_count=1,
                acknowledged_at=t + timedelta(minutes=3),
                resolved_at=t + timedelta(minutes=25) if status == AlertStatus.RESOLVED else None,
                resolution_note="Vehicle intercepted by PCR van (seed data)"
                if status == AlertStatus.RESOLVED
                else None,
            )
        )
    await db.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())
