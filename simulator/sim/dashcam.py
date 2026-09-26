"""Simulated okDriver dashcam on a patrol vehicle.

A mobile camera behaves differently from a fixed CCTV camera:
* it reports GPS telemetry (position, speed, heading) with every heartbeat over 4G
* its on-device ANPR reads plates of surrounding traffic *at the vehicle's current position*,
  so a watchlist hit is geo-located where the van is, not at a fixed pole
* it produces ADAS / driver-monitoring events (overspeed, harsh braking, collision warning,
  drowsiness) - the core okDriver dashcam feature set
"""

import asyncio
import logging
import math
import os
import random
import uuid
from datetime import UTC, datetime

import httpx

from sim.analytics import API, API_KEY, WATCHLIST_PLATES, random_plate

log = logging.getLogger("sim.dashcam")
CAMERA = os.getenv("DASHCAM_ID", "D001")
SPEED_LIMIT = 50.0
WATCHLIST_RATE = float(os.getenv("DASHCAM_WATCHLIST_PROBABILITY", "0.004"))

# Patrol loop through Ahmedabad West (approximate road junction coordinates)
ROUTE = [
    (23.01203, 72.56261),  # Paldi
    (23.02310, 72.57120),  # Ellisbridge
    (23.03390, 72.56980),  # Ashram Road
    (23.04500, 72.56900),  # Income Tax circle
    (23.03650, 72.56110),  # Navrangpura
    (23.04130, 72.54520),  # Helmet circle
    (23.03860, 72.52900),  # Vastrapur
    (23.02579, 72.50732),  # ISKCON cross roads
    (23.01200, 72.51000),  # Prahladnagar
    (23.01400, 72.52300),  # Anandnagar
    (23.02230, 72.53000),  # Shivranjani
    (23.01860, 72.54940),  # Nehru Nagar
]


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6_371_000
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


async def run_dashcam() -> None:
    rng = random.Random()
    tick = float(os.getenv("DASHCAM_TICK_S", "3"))
    # Simulation runs faster than real time so the van visibly moves on the map
    time_scale = float(os.getenv("DASHCAM_TIME_SCALE", "4"))
    leg, progress = 0, 0.0
    speed = 30.0
    await asyncio.sleep(12)
    log.info("dashcam %s on patrol (%d waypoints)", CAMERA, len(ROUTE))
    async with httpx.AsyncClient(base_url=API, headers={"X-API-Key": API_KEY}, timeout=5) as http:

        async def post(path: str, body: dict) -> None:
            try:
                r = await http.post(path, json=body)
                if r.status_code >= 400:
                    log.warning("%s -> %s %s", path, r.status_code, r.text[:160])
            except httpx.HTTPError as exc:
                log.warning("%s failed: %s", path, exc.__class__.__name__)

        while True:
            if os.path.exists("/tmp/dashcam-paused"):
                await asyncio.sleep(tick)
                continue
            a, b = ROUTE[leg], ROUTE[(leg + 1) % len(ROUTE)]
            prev_speed = speed
            speed = max(0.0, min(72.0, speed + rng.uniform(-8, 9)))
            harsh = rng.random() < 0.03
            if harsh:
                speed = max(0.0, prev_speed - rng.uniform(25, 35))
            progress += speed / 3.6 * tick * time_scale / max(haversine_m(a, b), 1)
            if progress >= 1:
                leg, progress = (leg + 1) % len(ROUTE), 0.0
                a, b = ROUTE[leg], ROUTE[(leg + 1) % len(ROUTE)]
            lat = a[0] + (b[0] - a[0]) * progress
            lng = a[1] + (b[1] - a[1]) * progress
            heading = bearing(a, b)
            now = datetime.now(UTC).isoformat()
            await post(
                f"/cameras/{CAMERA}/heartbeat",
                {
                    "latitude": round(lat, 6),
                    "longitude": round(lng, 6),
                    "speed_kmh": round(speed, 1),
                    "heading_deg": round(heading, 1),
                    "fps": 15,
                    "bitrate_kbps": round(rng.uniform(550, 800)),
                    "packet_loss_pct": round(rng.uniform(0, 2.5), 2),
                    "firmware": "okdriver-dc 4.2.0",
                },
            )

            base = {
                "camera_id": CAMERA,
                "timestamp": now,
                "latitude": round(lat, 6),
                "longitude": round(lng, 6),
                "speed_kmh": round(speed, 1),
                "model_name": "okdriver-edge-adas (simulated)",
            }
            # On-device ANPR of surrounding traffic
            if rng.random() < 0.45:
                plate = rng.choice(WATCHLIST_PLATES) if rng.random() < WATCHLIST_RATE else random_plate(rng)
                await post(
                    "/events",
                    {
                        **base,
                        "event_id": f"dc-{uuid.uuid4().hex[:20]}",
                        "event_type": "ANPR",
                        "vehicle_number": plate,
                        "confidence": round(rng.uniform(0.8, 0.97), 3),
                        "vehicle_type": rng.choice(["car", "motorcycle", "auto_rickshaw", "truck"]),
                        "bounding_box": {"x": rng.randint(300, 700), "y": rng.randint(300, 420), "w": 120, "h": 34},
                        "model_name": "okdriver-edge-anpr (simulated)",
                    },
                )
            # ADAS / driver-monitoring events
            adas = None
            if speed > SPEED_LIMIT + 10 and rng.random() < 0.5:
                adas = ("OVERSPEED", f"{speed:.0f} km/h in {SPEED_LIMIT:.0f} zone")
            elif harsh:
                adas = ("HARSH_BRAKING", f"{prev_speed:.0f}->{speed:.0f} km/h")
            elif rng.random() < 0.015:
                adas = ("COLLISION_WARNING", "time-to-collision 1.4 s")
            elif rng.random() < 0.008:
                adas = ("DRIVER_DROWSINESS", "eyes closed 1.8 s")
            if adas:
                await post(
                    "/events",
                    {
                        **base,
                        "event_id": f"dc-{uuid.uuid4().hex[:20]}",
                        "event_type": adas[0],
                        "confidence": round(rng.uniform(0.8, 0.97), 3),
                        "object_label": adas[1],
                    },
                )
            await asyncio.sleep(tick)
