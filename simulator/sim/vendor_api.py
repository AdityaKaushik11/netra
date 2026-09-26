"""Simulated proprietary NVR / cloud-VMS REST API.

Many Indian city deployments sit behind vendor NVRs that expose only REST status and JPEG
snapshot endpoints. This mock renders a synthetic traffic scene with an OSD overlay and lets
the demo flip a channel to weak/offline to show health transitions."""

import hmac
import io
import math
import os
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query, Response
from PIL import Image, ImageDraw, ImageFilter, ImageFont

API_KEY = os.getenv("VENDOR_API_KEY", "")
TZ = ZoneInfo(os.getenv("TZ", "Asia/Kolkata"))
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
CHANNELS = {
    1: {"name": "VAISHNODEVI CIRCLE  CH-01", "state": "online"},
    2: {"name": "SG HWY SERVICE RD  CH-02", "state": "online"},
}
STARTED = time.time()

app = FastAPI(title="Vendor NVR API (simulated)", docs_url=None, redoc_url=None)


def check_key(key: str | None) -> None:
    if not API_KEY or not key or not hmac.compare_digest(key, API_KEY):
        raise HTTPException(status_code=401, detail="invalid api key")


def channel(ch: int) -> dict:
    if ch not in CHANNELS:
        raise HTTPException(status_code=404, detail="no such channel")
    return CHANNELS[ch]


def _font(size: int):
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def render(ch: int) -> bytes:
    w, h = 960, 540
    t = time.time()
    img = Image.new("RGB", (w, h), (46, 52, 58))
    d = ImageDraw.Draw(img)
    # road in perspective
    d.polygon([(380, 120), (580, 120), (w, h), (0, h)], fill=(70, 74, 78))
    for i in range(12):
        y = 120 + ((i * 45 + t * 60) % 420)
        scale = (y - 120) / 420
        d.rectangle([478 - 2 - 4 * scale, y, 482 + 4 * scale, y + 10 + 20 * scale], fill=(220, 210, 90))
    # vehicles
    rng = random.Random(ch)
    for k in range(4):
        speed = 40 + rng.random() * 60
        lane = rng.choice([-1, 1])
        phase = (t * speed / 420 + k / 4) % 1.0
        y = 120 + phase * 420
        scale = 0.25 + phase * 1.2
        cx = 480 + lane * (60 + 180 * phase)
        cw, chh = 110 * scale, 70 * scale
        color = [(200, 200, 205), (170, 30, 30), (30, 60, 150), (20, 20, 20)][k]
        d.rounded_rectangle([cx - cw / 2, y - chh / 2, cx + cw / 2, y + chh / 2], radius=int(8 * scale), fill=color)
        d.rectangle([cx - 22 * scale, y + chh / 4, cx + 22 * scale, y + chh / 4 + 10 * scale], fill=(240, 240, 240))
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    noise = Image.effect_noise((w, h), 18).convert("RGB")
    img = Image.blend(img, noise, 0.08)
    d = ImageDraw.Draw(img)
    f = _font(20)
    d.rectangle([0, 0, w, 34], fill=(0, 0, 0))
    d.text((12, 6), channel(ch)["name"], font=f, fill=(255, 255, 255))
    stamp = datetime.now(TZ).strftime("%d-%m-%Y %H:%M:%S")
    d.text((w - 250, 6), stamp, font=f, fill=(255, 255, 255))
    if int(t) % 2 == 0:
        d.ellipse([w - 290, 11, w - 276, 25], fill=(220, 30, 30))
    d.text((12, h - 30), "NVR-X16  SNAPSHOT API", font=_font(14), fill=(200, 200, 200))
    if channel(ch)["state"] == "weak":
        img = img.filter(ImageFilter.GaussianBlur(3))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    return buf.getvalue()


@app.get("/vendor/api/v1/channels/{ch}/status")
async def status(ch: int, x_api_key: str | None = Header(None)):
    check_key(x_api_key)
    c = channel(ch)
    state = c["state"]
    fps = {"online": 10, "weak": 3, "offline": 0}[state]
    return {
        "channel": ch,
        "online": state != "offline",
        "signal": "weak" if state == "weak" else "good",
        "fps": fps,
        "uptime_s": int(time.time() - STARTED),
        "storage_used_pct": round(40 + 10 * math.sin(time.time() / 3600), 1),
        "message": "video loss" if state == "offline" else None,
    }


@app.get("/vendor/api/v1/channels/{ch}/snapshot.jpg")
async def snapshot(ch: int, x_api_key: str | None = Header(None)):
    check_key(x_api_key)
    if channel(ch)["state"] == "offline":
        raise HTTPException(status_code=503, detail="video loss")
    return Response(render(ch), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.post("/vendor/api/v1/channels/{ch}/simulate")
async def simulate(
    ch: int, state: str = Query(pattern="^(online|weak|offline)$"), x_api_key: str | None = Header(None)
):
    """Demo control: change the simulated channel condition."""
    check_key(x_api_key)
    channel(ch)["state"] = state
    return {"channel": ch, "state": state}
