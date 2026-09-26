import time
from datetime import datetime

import httpx

from app.adapters.base import CameraAdapter, ProbeResult
from app.core.config import get_settings
from app.core.netguard import UnsafeTarget, check_url
from app.core.security import decrypt_secret
from app.models import Camera
from app.models.enums import CameraStatus, SourceProtocol
from app.schemas.camera import PlaybackInfo


async def safe_get(url: str, *, timeout: float, headers: dict | None = None, max_redirects: int = 0) -> httpx.Response:
    """GET with the SSRF guard applied to the URL and to every redirect hop."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(max_redirects + 1):
            await check_url(url)
            r = await client.get(url, headers=headers)
            if not r.is_redirect:
                return r
            url = str(r.next_request.url) if r.next_request else url
        return r


class HlsAdapter(CameraAdapter):
    """A source that already publishes HLS (e.g. an existing municipal VMS or cloud camera)."""

    protocol = SourceProtocol.HLS

    async def probe(self, camera: Camera) -> ProbeResult:
        s = get_settings()
        started = time.perf_counter()
        try:
            r = await safe_get(camera.stream_endpoint, timeout=s.probe_timeout_s, max_redirects=3)
        except UnsafeTarget as exc:
            return ProbeResult(CameraStatus.OFFLINE, f"blocked endpoint: {exc}")
        except httpx.HTTPError as exc:
            return ProbeResult(CameraStatus.OFFLINE, f"manifest unreachable: {exc.__class__.__name__}")
        latency = time.perf_counter() - started
        metrics = {"manifest_ms": round(latency * 1000, 1)}
        if r.status_code != 200 or "#EXTM3U" not in r.text[:64]:
            return ProbeResult(CameraStatus.OFFLINE, f"invalid manifest (HTTP {r.status_code})", metrics)
        if latency > s.probe_slow_threshold_s:
            return ProbeResult(CameraStatus.DEGRADED, f"slow manifest ({latency:.1f}s)", metrics)
        return ProbeResult(CameraStatus.ONLINE, "manifest OK", metrics)

    def playback(self, camera: Camera, token: str, expires_at: datetime) -> PlaybackInfo:
        return PlaybackInfo(
            camera_id=camera.id,
            kind="hls",
            url=camera.stream_endpoint,
            token=None,
            note="Direct HLS from an existing publisher",
        )


class VendorApiAdapter(CameraAdapter):
    """Proprietary NVR / cloud VMS exposing REST status and snapshot endpoints with an API key.
    The key stays on the server; browsers get snapshots through a signed proxy URL."""

    protocol = SourceProtocol.VENDOR_API

    def headers(self, camera: Camera) -> dict[str, str]:
        key = decrypt_secret(camera.stream_secret_enc)
        return {"X-Api-Key": key} if key else {}

    async def probe(self, camera: Camera) -> ProbeResult:
        s = get_settings()
        url = camera.stream_endpoint.rstrip("/") + "/status"
        try:
            r = await safe_get(url, timeout=s.probe_timeout_s, headers=self.headers(camera))
        except UnsafeTarget as exc:
            return ProbeResult(CameraStatus.OFFLINE, f"blocked endpoint: {exc}")
        except httpx.HTTPError as exc:
            return ProbeResult(CameraStatus.OFFLINE, f"vendor API unreachable: {exc.__class__.__name__}")
        if r.status_code in (401, 403):
            return ProbeResult(CameraStatus.OFFLINE, "vendor API rejected credentials")
        if r.status_code != 200:
            return ProbeResult(CameraStatus.OFFLINE, f"vendor API HTTP {r.status_code}")
        data = r.json()
        metrics = {k: data.get(k) for k in ("fps", "signal", "uptime_s", "storage_used_pct") if k in data}
        if not data.get("online", False):
            return ProbeResult(CameraStatus.OFFLINE, data.get("message") or "vendor reports channel offline", metrics)
        if data.get("signal") == "weak" or (data.get("fps") or 99) < 5:
            return ProbeResult(CameraStatus.DEGRADED, "vendor reports weak signal / low fps", metrics)
        return ProbeResult(CameraStatus.ONLINE, "vendor API OK", metrics)

    def playback(self, camera: Camera, token: str, expires_at: datetime) -> PlaybackInfo:
        return PlaybackInfo(
            camera_id=camera.id,
            kind="snapshot",
            url=f"/api/v1/cameras/{camera.id}/snapshot",
            token=token,
            expires_at=expires_at,
            note="Near-live snapshots proxied from vendor API (1 fps)",
        )
