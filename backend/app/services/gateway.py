"""Client for the video gateway (MediaMTX control API v3).

The gateway pulls camera RTSP streams on the private camera network and re-publishes them as
LL-HLS / WebRTC for browsers. Camera credentials are injected here, server-side, so they never
reach an operator's browser."""

import logging
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)


def with_credentials(url: str, username: str | None, password: str | None) -> str:
    if not username:
        return url
    parts = urlsplit(url)
    netloc = f"{quote(username, safe='')}:{quote(password or '', safe='')}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def path_name(camera_id: str) -> str:
    return f"cam-{camera_id.lower()}"


class GatewayClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return get_settings().gateway_enabled

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            s = get_settings()
            auth = (s.gateway_api_user, s.gateway_api_secret) if s.gateway_api_secret else None
            self._client = httpx.AsyncClient(base_url=s.gateway_api_url, timeout=5, auth=auth)
        return self._client

    async def upsert_path(self, name: str, source: str, record: bool = False) -> bool:
        if not self.enabled:
            return False
        conf = {
            "source": source,
            "sourceOnDemand": get_settings().stream_on_demand,
            "rtspTransport": "tcp",
            "record": record,
        }
        http = self._http()
        try:
            r = await http.post(f"/v3/config/paths/replace/{name}", json=conf)
            if r.status_code == 404:
                r = await http.post(f"/v3/config/paths/add/{name}", json=conf)
            if r.status_code >= 400:
                log.warning("gateway upsert %s failed: %s %s", name, r.status_code, r.text[:200])
                return False
            return True
        except httpx.HTTPError as exc:
            log.warning("gateway unreachable while registering %s: %s", name, exc)
            return False

    async def delete_path(self, name: str) -> None:
        if not self.enabled:
            return
        try:
            await self._http().delete(f"/v3/config/paths/delete/{name}")
        except httpx.HTTPError as exc:
            log.warning("gateway delete %s failed: %s", name, exc)

    async def path_state(self, name: str) -> dict | None:
        """Returns runtime state of a path, or None if the path is not registered."""
        r = await self._http().get(f"/v3/paths/get/{name}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    async def list_paths(self) -> list[dict]:
        r = await self._http().get("/v3/paths/list", params={"itemsPerPage": 1000})
        r.raise_for_status()
        return r.json().get("items", [])

    async def list_recordings(self, name: str, token: str) -> list[dict]:
        """Recorded segments of a path from the gateway playback server."""
        async with httpx.AsyncClient(base_url=get_settings().gateway_playback_url, timeout=5) as client:
            r = await client.get("/list", params={"path": name, "token": token})
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


gateway = GatewayClient()
