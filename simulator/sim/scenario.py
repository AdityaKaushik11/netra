"""Scripted demo scenarios.

python -m sim.scenario trace GJ01XX0001        # vehicle crosses C001 -> C002 -> C005 -> C006
python -m sim.scenario trace GJ01XX0001 --live # same, but one sighting every 8 s (for the video)
python -m sim.scenario clone GJ01XX2468        # same plate 15 km apart in 2 min (cloned plate)
python -m sim.scenario burst GJ01XX0001 C001   # 10 repeat reads in 3 s -> 1 event, repeat_count 9
python -m sim.scenario onboard cameras.json    # API-based bulk camera onboarding
python -m sim.scenario vendor C005 weak|offline|online
"""

import argparse
import asyncio
import json
import os
import random
from datetime import UTC, datetime, timedelta

import httpx

from sim.analytics import API, API_KEY, Sender, anpr_event

ROUTE = [("C001", -39), ("C002", -23), ("C005", 0)]  # minutes relative to now (10:02, 10:18, 10:41)


async def trace(plate: str, live: bool, extend: bool) -> None:
    """Timestamps follow the brief's example (10:02 -> 10:18 -> 10:41, i.e. -39/-23/0 min).
    --live only paces delivery so alerts pop up one after another on camera."""
    sender = Sender(mode="http")
    rng = random.Random()
    route = [("C001", -55), ("C002", -39), ("C005", -23), ("C006", 0)] if extend else ROUTE
    now = datetime.now(UTC)
    for i, (camera, offset) in enumerate(route):
        when = now + timedelta(minutes=offset)
        ev = anpr_event(camera, plate, rng, when=when, vehicle_type="car", vehicle_color="white")
        ev["confidence"] = round(rng.uniform(0.9, 0.98), 3)
        result = await sender.send(ev)
        print(f"[{when.astimezone().strftime('%H:%M:%S')}] {plate} @ {camera}: {result}")
        if live and i < len(route) - 1:
            await asyncio.sleep(8)
    await sender.close()


async def clone(plate: str) -> None:
    sender = Sender(mode="http")
    rng = random.Random()
    now = datetime.now(UTC)
    for camera, offset in [("C001", -2), ("C006", 0)]:
        ev = anpr_event(camera, plate, rng, when=now + timedelta(minutes=offset))
        print(camera, await sender.send(ev))
    await sender.close()


async def burst(plate: str, camera: str) -> None:
    sender = Sender(mode="http")
    rng = random.Random()
    for _ in range(10):
        r = await sender.http.post("/events", json=anpr_event(camera, plate, rng))
        print(r.status_code, r.json().get("status"), r.json().get("event_id"))
        await asyncio.sleep(0.3)
    await sender.close()


async def onboard(path: str) -> None:
    with open(path) as fh:
        raw = fh.read()
    # Sample file ships with placeholders; fill them from the environment (never commit secrets)
    raw = raw.replace("replace-with-camsim-password", os.getenv("CAMSIM_PASSWORD", ""))
    raw = raw.replace("replace-with-vendor-api-key", os.getenv("VENDOR_API_KEY", ""))
    payload = json.loads(raw)
    async with httpx.AsyncClient(base_url=API, headers={"X-API-Key": API_KEY}, timeout=20) as http:
        r = await http.post("/cameras/bulk", json=payload)
        print(r.status_code, json.dumps(r.json(), indent=2))


async def vendor(state: str, channel: int) -> None:
    base = os.getenv("VENDOR_BASE", "http://localhost:8090")
    async with httpx.AsyncClient(timeout=5) as http:
        r = await http.post(
            f"{base}/vendor/api/v1/channels/{channel}/simulate",
            params={"state": state},
            headers={"X-Api-Key": os.getenv("VENDOR_API_KEY", "")},
        )
        print(r.status_code, r.text)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trace")
    t.add_argument("plate", nargs="?", default="GJ01XX0001")
    t.add_argument("--live", action="store_true")
    t.add_argument("--extend", action="store_true", help="also pass CH-0 Gandhinagar (C006)")
    c = sub.add_parser("clone")
    c.add_argument("plate", nargs="?", default="GJ01XX2468")
    b = sub.add_parser("burst")
    b.add_argument("plate", nargs="?", default="GJ01XX0001")
    b.add_argument("camera", nargs="?", default="C001")
    o = sub.add_parser("onboard")
    o.add_argument("path")
    v = sub.add_parser("vendor")
    v.add_argument("state", choices=["online", "weak", "offline"])
    v.add_argument("--channel", type=int, default=1)
    a = p.parse_args()
    if a.cmd == "trace":
        asyncio.run(trace(a.plate, a.live, a.extend))
    elif a.cmd == "clone":
        asyncio.run(clone(a.plate))
    elif a.cmd == "burst":
        asyncio.run(burst(a.plate, a.camera))
    elif a.cmd == "onboard":
        asyncio.run(onboard(a.path))
    elif a.cmd == "vendor":
        asyncio.run(vendor(a.state, a.channel))


if __name__ == "__main__":
    main()
