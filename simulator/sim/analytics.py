"""Simulated AI analytics engine (stands in for an edge ANPR / detection model).

Produces realistic inference traffic:
* ANPR reads arrive in bursts (a passing vehicle is read several times) -> exercises dedup
* occasional watchlist vehicles, sometimes with OCR errors -> exact + fuzzy matching
* occasional face-recognition / person / object detections
* delivery over REST (X-API-Key) or a Redis Stream message channel, with retries and a stable
  event_id so retries are idempotent
"""

import asyncio
import json
import logging
import os
import random
import time
import uuid
from datetime import UTC, datetime

import httpx
import redis.asyncio as redis

log = logging.getLogger("sim.analytics")

API = os.getenv("NETRA_API_URL", "http://backend:8000/api/v1")
API_KEY = os.getenv("SEED_API_KEY", "")
MODE = os.getenv("INGEST_MODE", "mixed")  # http | stream | mixed
REDIS_URL = os.getenv("REDIS_URL", "")
STREAM_KEY = os.getenv("STREAM_INGEST_KEY", "netra:ingest:detections")
CAMERAS = [c.strip() for c in os.getenv("SIM_CAMERAS", "C001,C002,C003,C005,C006").split(",") if c.strip()]
RATE = float(os.getenv("SIM_EVENTS_PER_MIN", "20"))
WATCHLIST_RATE = float(os.getenv("SIM_WATCHLIST_PROBABILITY", "0.008"))
WATCHLIST_PLATES = ["GJ05XX1234", "GJ18XX4321", "GJ27XX7788", "MH12XX9090", "GJ01XX5555", "RJ14XX3030", "GJ01XX9999"]
WATCHLIST_PERSONS = ["FR-SYN-000123", "FR-SYN-000456", "FR-SYN-000789"]
OCR_CONFUSIONS = {"0": "O", "O": "0", "1": "I", "8": "B", "5": "S", "2": "Z"}
STATES = ["GJ01", "GJ01", "GJ01", "GJ18", "GJ27", "GJ05", "GJ06", "GJ38", "MH12", "RJ14"]
VEHICLES = ["car", "car", "car", "motorcycle", "motorcycle", "auto_rickshaw", "truck", "bus", "suv"]
COLORS = ["white", "silver", "black", "grey", "red", "blue"]
MODEL = "anpr-yolov8n+paddleocr-v4 (simulated)"


def random_plate(rng: random.Random) -> str:
    letters = "ABCDEFGHJKLMNPRSTUVWZ"
    return f"{rng.choice(STATES)}{rng.choice(letters)}{rng.choice(letters)}{rng.randint(1, 9999):04d}"


def ocr_error(plate: str, rng: random.Random) -> str:
    idx = [i for i, ch in enumerate(plate) if ch in OCR_CONFUSIONS and i > 3]
    if not idx:
        return plate
    i = rng.choice(idx)
    return plate[:i] + OCR_CONFUSIONS[plate[i]] + plate[i + 1 :]


def anpr_event(camera: str, plate: str, rng: random.Random, when: datetime | None = None, **kw) -> dict:
    return {
        "event_id": f"sim-{uuid.uuid4().hex[:20]}",
        "camera_id": camera,
        "event_type": "ANPR",
        "timestamp": (when or datetime.now(UTC)).isoformat(),
        "vehicle_number": plate,
        "confidence": round(rng.uniform(0.78, 0.99), 3),
        "vehicle_type": rng.choice(VEHICLES),
        "vehicle_color": rng.choice(COLORS),
        "bounding_box": {"x": rng.randint(200, 900), "y": rng.randint(300, 600), "w": 180, "h": 48},
        "model_name": MODEL,
        **kw,
    }


class Sender:
    def __init__(self, mode: str = MODE) -> None:
        self.mode = mode
        self.http = httpx.AsyncClient(base_url=API, headers={"X-API-Key": API_KEY}, timeout=10)
        self.redis = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None
        self.rng = random.Random()

    async def send(self, event: dict) -> dict | None:
        use_stream = self.redis is not None and (
            self.mode == "stream" or (self.mode == "mixed" and self.rng.random() < 0.5)
        )
        if use_stream:
            await self.redis.xadd(STREAM_KEY, {"payload": json.dumps(event), "client": "analytics-sim"}, maxlen=100_000)
            return {"status": "queued"}
        for attempt in range(4):  # retries are safe: event_id makes ingestion idempotent
            try:
                r = await self.http.post("/events", json=event)
                if r.status_code in (200, 201):
                    return r.json()
                if r.status_code < 500 and r.status_code != 429:
                    log.warning("event rejected %s: %s", r.status_code, r.text[:200])
                    return None
            except httpx.HTTPError as exc:
                log.warning("send failed (%s), retrying", exc.__class__.__name__)
            await asyncio.sleep(0.5 * 2**attempt)
        return None

    async def close(self) -> None:
        await self.http.aclose()
        if self.redis is not None:
            await self.redis.aclose()


async def run_background_traffic() -> None:
    rng = random.Random()
    sender = Sender()
    log.info("analytics simulator: %.0f vehicles/min over %s via %s", RATE, CAMERAS, MODE)
    await asyncio.sleep(15)  # let the API come up
    while True:
        camera = rng.choice(CAMERAS)
        roll = rng.random()
        if roll < WATCHLIST_RATE:
            plate = rng.choice(WATCHLIST_PLATES)
            if rng.random() < 0.3:
                plate = ocr_error(plate, rng)  # exercise fuzzy matching
        else:
            plate = random_plate(rng)
        # A passing vehicle is read 1-4 times within a couple of seconds
        for i in range(rng.choice([1, 1, 2, 3, 4])):
            await sender.send(anpr_event(camera, plate, rng))
            if i:
                await asyncio.sleep(rng.uniform(0.2, 0.8))
        if rng.random() < 0.04:
            # Face-recognition match against the gallery (occasionally a watchlisted person)
            ref = rng.choice(WATCHLIST_PERSONS) if rng.random() < 0.1 else f"FR-SYN-{rng.randint(100000, 999999)}"
            await sender.send(
                {
                    "event_id": f"sim-{uuid.uuid4().hex[:20]}",
                    "camera_id": rng.choice(CAMERAS),
                    "event_type": "FACE_RECOGNITION",
                    "timestamp": datetime.now(UTC).isoformat(),
                    "person_ref": ref,
                    "confidence": round(rng.uniform(0.7, 0.95), 3),
                    "bounding_box": {"x": 420, "y": 140, "w": 64, "h": 80},
                    "model_name": "arcface-r100 (simulated)",
                }
            )
        if rng.random() < 0.05:
            event_type, labels = rng.choice(
                [
                    ("PERSON_DETECTION", ["person loitering", "crowd forming"]),
                    ("OBJECT_DETECTION", ["abandoned bag", "two-wheeler rider without helmet", "wrong-way vehicle"]),
                ]
            )
            await sender.send(
                {
                    "event_id": f"sim-{uuid.uuid4().hex[:20]}",
                    "camera_id": rng.choice(CAMERAS),
                    "event_type": event_type,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "confidence": round(rng.uniform(0.6, 0.95), 3),
                    "object_label": rng.choice(labels),
                    "bounding_box": {"x": 300, "y": 200, "w": 90, "h": 200},
                    "model_name": "yolov8s-coco (simulated)",
                }
            )
        await asyncio.sleep(max(0.2, rng.expovariate(RATE / 60)))


async def run_edge_heartbeats() -> None:
    """Edge agent co-located with cameras that are monitored in HEARTBEAT mode."""
    cameras = [c.strip() for c in os.getenv("HEARTBEAT_CAMERAS", "C006").split(",") if c.strip()]
    if not cameras:
        return
    rng = random.Random()
    started = time.monotonic()
    async with httpx.AsyncClient(base_url=API, headers={"X-API-Key": API_KEY}, timeout=5) as http:
        await asyncio.sleep(10)
        while True:
            if not os.path.exists("/tmp/edge-agent-paused"):
                for cam in cameras:
                    try:
                        await http.post(
                            f"/cameras/{cam}/heartbeat",
                            json={
                                "fps": round(rng.uniform(14, 15), 1),
                                "bitrate_kbps": round(rng.uniform(700, 900)),
                                "packet_loss_pct": round(rng.uniform(0, 0.8), 2),
                                "uptime_s": int(time.monotonic() - started),
                                "temperature_c": round(rng.uniform(38, 46), 1),
                                "firmware": "edge-agent 1.3.0",
                            },
                        )
                    except httpx.HTTPError as exc:
                        log.warning("heartbeat failed: %s", exc.__class__.__name__)
            await asyncio.sleep(10)
