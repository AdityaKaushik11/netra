import asyncio
import time
from datetime import datetime
from urllib.parse import urlsplit

import httpx

from app.adapters.base import CameraAdapter, ProbeResult
from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.models import Camera
from app.models.enums import CameraStatus, SourceProtocol
from app.schemas.camera import PlaybackInfo
from app.services.gateway import gateway, path_name, with_credentials

MIN_HEALTHY_KBPS = 40.0
_last_bytes: dict[str, tuple[int, float]] = {}


async def tcp_reachable(url: str, default_port: int, timeout: float) -> tuple[bool, float]:
    parts = urlsplit(url)
    started = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(parts.hostname, parts.port or default_port), timeout)
        writer.close()
        return True, time.perf_counter() - started
    except (OSError, TimeoutError):
        return False, time.perf_counter() - started


async def probe_gateway_path(camera: Camera, source_url: str) -> ProbeResult:
    """Health from the gateway's view of the pull: registered? ready? bytes flowing?"""
    s = get_settings()
    name = camera.gateway_path or path_name(camera.id)
    if not gateway.enabled:
        ok, rtt = await tcp_reachable(source_url, 554, s.probe_timeout_s)
        return ProbeResult(
            CameraStatus.ONLINE if ok else CameraStatus.OFFLINE,
            "TCP reachable (gateway disabled)" if ok else "RTSP port unreachable",
            {"rtt_ms": round(rtt * 1000, 1)},
        )
    try:
        state = await gateway.path_state(name)
    except httpx.HTTPError as exc:
        return ProbeResult(CameraStatus.UNKNOWN, f"gateway unreachable: {exc.__class__.__name__}")
    if state is None:
        return ProbeResult(CameraStatus.OFFLINE, "stream not registered on gateway")
    ready = bool(state.get("ready", state.get("available")))
    if not ready:
        _last_bytes.pop(name, None)
        return ProbeResult(CameraStatus.OFFLINE, "gateway cannot pull stream from source")
    received = int(state.get("bytesReceived", 0))
    now = time.monotonic()
    metrics: dict = {
        "readers": len(state.get("readers") or []),
        "tracks": state.get("tracks"),
    }
    prev = _last_bytes.get(name)
    _last_bytes[name] = (received, now)
    if prev and now > prev[1]:
        kbps = (received - prev[0]) * 8 / 1000 / (now - prev[1])
        metrics["bitrate_kbps"] = round(kbps, 1)
        if kbps < MIN_HEALTHY_KBPS:
            return ProbeResult(CameraStatus.DEGRADED, f"low inbound bitrate ({kbps:.0f} kbps)", metrics)
    return ProbeResult(CameraStatus.ONLINE, "stream ready on gateway", metrics)


def hls_playback(camera: Camera, token: str, expires_at: datetime) -> PlaybackInfo:
    name = camera.gateway_path or path_name(camera.id)
    base = get_settings().gateway_public_hls_base.rstrip("/")
    return PlaybackInfo(
        camera_id=camera.id,
        kind="hls",
        url=f"{base}/{name}/index.m3u8",
        webrtc_url=f"/webrtc/{name}/whep",
        token=token,
        expires_at=expires_at,
        note="Relayed by the video gateway (RTSP -> LL-HLS)",
    )


class RtspAdapter(CameraAdapter):
    protocol = SourceProtocol.RTSP

    def source_url(self, camera: Camera) -> str:
        return with_credentials(
            camera.stream_endpoint, camera.stream_username, decrypt_secret(camera.stream_secret_enc)
        )

    async def prepare(self, camera: Camera) -> None:
        camera.gateway_path = path_name(camera.id)
        await gateway.upsert_path(camera.gateway_path, self.source_url(camera), camera.recording_enabled)

    async def teardown(self, camera: Camera) -> None:
        if camera.gateway_path:
            await gateway.delete_path(camera.gateway_path)

    async def probe(self, camera: Camera) -> ProbeResult:
        result = await probe_gateway_path(camera, camera.stream_endpoint)
        if result.reason == "stream not registered on gateway" and gateway.enabled:
            await self.prepare(camera)  # self-heal after a gateway restart
        return result

    def playback(self, camera: Camera, token: str, expires_at: datetime) -> PlaybackInfo:
        return hls_playback(camera, token, expires_at)
