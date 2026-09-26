"""Outbound-request guard (SSRF protection).

Camera endpoints are supplied by administrators and API clients, and the platform connects to
them (health probes, ONVIF SOAP, vendor snapshots). Without a guard, a "camera" could point at
the platform's own infrastructure (database, Redis, gateway control API) or at a cloud metadata
service, and the snapshot proxy would even return the response.

Rules:
* Private (RFC 1918) addresses are allowed - real cameras live on private VLANs.
* Loopback, link-local (incl. 169.254.169.254 metadata), multicast, reserved and unspecified
  addresses are refused.
* Hostnames of the platform's own services, and every IP they resolve to, are refused.
* Checks run when an endpoint is saved and again, after DNS resolution, before every outbound
  request (defeats DNS rebinding and names that resolve to internal addresses).
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from app.core.config import get_settings


class UnsafeTarget(ValueError):
    pass


def _blocked_hosts() -> set[str]:
    return {h.strip().lower() for h in get_settings().blocked_endpoint_hosts.split(",") if h.strip()}


def _ip_forbidden(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified


def check_url_static(url: str) -> None:
    """Validation without DNS (used when a camera is created or edited)."""
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    if not host:
        raise UnsafeTarget("endpoint has no host")
    if host in _blocked_hosts() or host.endswith(".internal") or host == "localhost":
        raise UnsafeTarget(f"endpoint host '{host}' is a platform service and cannot be used as a camera")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if _ip_forbidden(ip):
        raise UnsafeTarget(f"endpoint address {ip} is not allowed (loopback / link-local / reserved)")


_internal_ips: tuple[float, set[str]] = (0.0, set())


async def _platform_ips() -> set[str]:
    """IP addresses of the platform's own services (cached for 60 s)."""
    global _internal_ips
    loop = asyncio.get_running_loop()
    if loop.time() - _internal_ips[0] < 60:
        return _internal_ips[1]
    ips: set[str] = set()
    for host in _blocked_hosts():
        try:
            infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            continue
        ips.update(i[4][0] for i in infos)
    _internal_ips = (loop.time(), ips)
    return ips


async def check_url(url: str) -> None:
    """Full check including DNS resolution; call immediately before connecting."""
    check_url_static(url)
    parts = urlsplit(url)
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(parts.hostname, parts.port or 80, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise UnsafeTarget(f"cannot resolve {parts.hostname}") from exc
    internal = await _platform_ips()
    for info in infos:
        addr = info[4][0]
        if _ip_forbidden(ipaddress.ip_address(addr)) or addr in internal:
            raise UnsafeTarget(f"{parts.hostname} resolves to a forbidden address")
