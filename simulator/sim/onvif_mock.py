"""Mock ONVIF Profile S device (Device + Media services over SOAP 1.2).

Verifies WS-Security UsernameToken PasswordDigest exactly like a real camera, and answers
GetDeviceInformation, GetProfiles and GetStreamUri. GetStreamUri points at the simulated RTSP
camera so the platform's ONVIF adapter exercises the full discover -> resolve -> pull flow."""

import base64
import hashlib
import hmac
import os
import xml.etree.ElementTree as ET

from fastapi import FastAPI, Request, Response

NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",
    "wsse": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd",
    "wsu": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd",
}
USER = os.getenv("ONVIF_USER", "admin")
PASSWORD = os.getenv("ONVIF_PASSWORD", "")
STREAM_URI = os.getenv("ONVIF_STREAM_URI", "rtsp://camsim:8554/c003")

app = FastAPI(title="Mock ONVIF device", docs_url=None, redoc_url=None)


def envelope(body: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
        'xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:trt="http://www.onvif.org/ver10/media/wsdl" '
        f'xmlns:tt="http://www.onvif.org/ver10/schema"><s:Body>{body}</s:Body></s:Envelope>'
    )


def fault(reason: str, status: int) -> Response:
    body = (
        "<s:Fault><s:Code><s:Value>s:Sender</s:Value><s:Subcode><s:Value>ter:NotAuthorized</s:Value>"
        f"</s:Subcode></s:Code><s:Reason><s:Text>{reason}</s:Text></s:Reason></s:Fault>"
    )
    return Response(envelope(body), status_code=status, media_type="application/soap+xml")


def authorised(root: ET.Element) -> bool:
    token = root.find(".//wsse:UsernameToken", NS)
    if token is None:
        return False
    user = token.findtext("wsse:Username", default="", namespaces=NS)
    digest = token.findtext("wsse:Password", default="", namespaces=NS)
    nonce = token.findtext("wsse:Nonce", default="", namespaces=NS)
    created = token.findtext("wsu:Created", default="", namespaces=NS)
    try:
        expected = base64.b64encode(
            hashlib.sha1(base64.b64decode(nonce) + created.encode() + PASSWORD.encode()).digest()
        ).decode()
    except ValueError:
        return False
    return hmac.compare_digest(user, USER) and hmac.compare_digest(digest, expected)


@app.post("/onvif/device_service")
async def device_service(request: Request) -> Response:
    raw = await request.body()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return fault("Malformed SOAP", 400)
    if not authorised(root):
        return fault("Sender not authorized", 401)
    text = raw.decode(errors="ignore")
    if "GetDeviceInformation" in text:
        body = (
            "<tds:GetDeviceInformationResponse><tds:Manufacturer>NetraSim</tds:Manufacturer>"
            "<tds:Model>PTZ-1 (ONVIF Profile S mock)</tds:Model><tds:FirmwareVersion>2.4.1</tds:FirmwareVersion>"
            "<tds:SerialNumber>NS-PTZ1-000031</tds:SerialNumber><tds:HardwareId>ns-hw-31</tds:HardwareId>"
            "</tds:GetDeviceInformationResponse>"
        )
    elif "GetProfiles" in text:
        body = (
            '<trt:GetProfilesResponse><trt:Profiles token="profile_main" fixed="true">'
            "<tt:Name>MainStream</tt:Name></trt:Profiles>"
            '<trt:Profiles token="profile_sub" fixed="true"><tt:Name>SubStream</tt:Name></trt:Profiles>'
            "</trt:GetProfilesResponse>"
        )
    elif "GetStreamUri" in text:
        body = (
            f"<trt:GetStreamUriResponse><trt:MediaUri><tt:Uri>{STREAM_URI}</tt:Uri>"
            "<tt:InvalidAfterConnect>false</tt:InvalidAfterConnect><tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>"
            "<tt:Timeout>PT0S</tt:Timeout></trt:MediaUri></trt:GetStreamUriResponse>"
        )
    else:
        return fault("Action not supported by mock", 400)
    return Response(envelope(body), media_type="application/soap+xml")
