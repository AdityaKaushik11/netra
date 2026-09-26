"""Minimal ONVIF client (Device + Media services, SOAP 1.2, WS-Security UsernameToken digest).

Implemented directly over HTTP so it works against any ONVIF Profile S device and against the
bundled mock device. Only the calls the platform needs are implemented:
GetDeviceInformation, GetProfiles and GetStreamUri."""

import base64
import hashlib
import os
from datetime import UTC, datetime
from xml.sax.saxutils import escape

import httpx
from defusedxml import ElementTree as ET

from app.adapters.base import CameraAdapter, ProbeResult
from app.adapters.rtsp import hls_playback, probe_gateway_path
from app.core.config import get_settings
from app.core.netguard import UnsafeTarget, check_url
from app.core.security import decrypt_secret
from app.models import Camera
from app.models.enums import CameraStatus, SourceProtocol
from app.schemas.camera import PlaybackInfo
from app.services.gateway import gateway, path_name, with_credentials

NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",
    "tds": "http://www.onvif.org/ver10/device/wsdl",
    "trt": "http://www.onvif.org/ver10/media/wsdl",
    "tt": "http://www.onvif.org/ver10/schema",
}


class OnvifError(Exception):
    pass


def _security_header(username: str | None, password: str | None) -> str:
    if not username:
        return ""
    nonce = os.urandom(16)
    created = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + (password or "").encode()).digest()).decode()
    return f"""<s:Header><Security s:mustUnderstand="1" xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd">
<UsernameToken><Username>{escape(username)}</Username>
<Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">{digest}</Password>
<Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-soap-message-security-1.0#Base64Binary">{base64.b64encode(nonce).decode()}</Nonce>
<Created xmlns="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">{created}</Created>
</UsernameToken></Security></s:Header>"""


async def _call(url: str, body: str, username: str | None, password: str | None) -> ET:
    envelope = (
        f'<?xml version="1.0" encoding="UTF-8"?><s:Envelope xmlns:s="{NS["s"]}" '
        f'xmlns:tds="{NS["tds"]}" xmlns:trt="{NS["trt"]}" xmlns:tt="{NS["tt"]}">'
        f"{_security_header(username, password)}<s:Body>{body}</s:Body></s:Envelope>"
    )
    try:
        await check_url(url)
    except UnsafeTarget as exc:
        raise OnvifError(f"blocked endpoint: {exc}") from exc
    try:
        async with httpx.AsyncClient(timeout=get_settings().probe_timeout_s) as client:
            r = await client.post(
                url, content=envelope, headers={"Content-Type": "application/soap+xml; charset=utf-8"}
            )
    except httpx.HTTPError as exc:
        raise OnvifError(f"device unreachable: {exc.__class__.__name__}") from exc
    if r.status_code == 401 or b"NotAuthorized" in r.content:
        raise OnvifError("ONVIF authentication failed")
    if r.status_code >= 400:
        raise OnvifError(f"ONVIF fault HTTP {r.status_code}")
    return ET.fromstring(r.content)


def _text(root, path: str) -> str | None:
    el = root.find(path, NS)
    return el.text if el is not None else None


async def get_device_information(url: str, username: str | None, password: str | None) -> dict:
    root = await _call(url, "<tds:GetDeviceInformation/>", username, password)
    base = ".//tds:GetDeviceInformationResponse/"
    return {
        "manufacturer": _text(root, base + "tds:Manufacturer"),
        "model": _text(root, base + "tds:Model"),
        "firmware": _text(root, base + "tds:FirmwareVersion"),
        "serial": _text(root, base + "tds:SerialNumber"),
        "hardware_id": _text(root, base + "tds:HardwareId"),
    }


async def get_stream_uri(url: str, username: str | None, password: str | None) -> str:
    root = await _call(url, "<trt:GetProfiles/>", username, password)
    profile = root.find(".//trt:Profiles", NS)
    if profile is None:
        raise OnvifError("device exposes no media profiles")
    token = profile.get("token")
    body = (
        "<trt:GetStreamUri><trt:StreamSetup><tt:Stream>RTP-Unicast</tt:Stream>"
        "<tt:Transport><tt:Protocol>RTSP</tt:Protocol></tt:Transport></trt:StreamSetup>"
        f"<trt:ProfileToken>{escape(token or '')}</trt:ProfileToken></trt:GetStreamUri>"
    )
    root = await _call(url, body, username, password)
    uri = _text(root, ".//trt:MediaUri/tt:Uri")
    if not uri:
        raise OnvifError("GetStreamUri returned no URI")
    return uri


class OnvifAdapter(CameraAdapter):
    protocol = SourceProtocol.ONVIF

    def _creds(self, camera: Camera) -> tuple[str | None, str | None]:
        return camera.stream_username, decrypt_secret(camera.stream_secret_enc)

    async def prepare(self, camera: Camera) -> None:
        user, pwd = self._creds(camera)
        try:
            uri = await get_stream_uri(camera.stream_endpoint, user, pwd)
        except OnvifError:
            return  # health monitor will report the failure and retry
        camera.resolved_stream_uri = uri
        camera.gateway_path = path_name(camera.id)
        await gateway.upsert_path(camera.gateway_path, with_credentials(uri, user, pwd), camera.recording_enabled)

    async def teardown(self, camera: Camera) -> None:
        if camera.gateway_path:
            await gateway.delete_path(camera.gateway_path)

    async def probe(self, camera: Camera) -> ProbeResult:
        user, pwd = self._creds(camera)
        try:
            info = await get_device_information(camera.stream_endpoint, user, pwd)
        except OnvifError as exc:
            return ProbeResult(CameraStatus.OFFLINE, f"ONVIF: {exc}")
        if not camera.resolved_stream_uri or not camera.gateway_path:
            await self.prepare(camera)
            if not camera.resolved_stream_uri:
                return ProbeResult(CameraStatus.DEGRADED, "ONVIF device up but stream URI unresolved")
        result = await probe_gateway_path(camera, camera.resolved_stream_uri)
        if result.reason == "stream not registered on gateway" and gateway.enabled:
            await self.prepare(camera)
        result.metrics["device"] = f"{info.get('manufacturer')} {info.get('model')}"
        return result

    def playback(self, camera: Camera, token: str, expires_at: datetime) -> PlaybackInfo:
        info = hls_playback(camera, token, expires_at)
        info.note = "ONVIF GetStreamUri -> RTSP -> gateway LL-HLS"
        return info
