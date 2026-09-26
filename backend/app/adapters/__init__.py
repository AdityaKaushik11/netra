from app.adapters.base import CameraAdapter, ProbeResult
from app.adapters.http_sources import HlsAdapter, VendorApiAdapter
from app.adapters.onvif import OnvifAdapter
from app.adapters.rtsp import RtspAdapter
from app.models.enums import SourceProtocol

_REGISTRY: dict[SourceProtocol, CameraAdapter] = {
    a.protocol: a for a in (RtspAdapter(), OnvifAdapter(), HlsAdapter(), VendorApiAdapter())
}


def get_adapter(protocol: SourceProtocol) -> CameraAdapter:
    return _REGISTRY[protocol]


__all__ = ["CameraAdapter", "ProbeResult", "get_adapter"]
