"""Camera source adapters.

Every heterogeneous source (RTSP IP camera, ONVIF device, existing HLS publisher, proprietary
vendor NVR/cloud API) is hidden behind one interface so the rest of the platform — registry,
health monitor, live view, analytics — never branches on vendor specifics. Adding a new
vendor SDK means adding one adapter class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.models import Camera
from app.models.enums import CameraStatus, SourceProtocol
from app.schemas.camera import PlaybackInfo


@dataclass
class ProbeResult:
    status: CameraStatus
    reason: str
    metrics: dict = field(default_factory=dict)


class CameraAdapter(ABC):
    protocol: SourceProtocol

    async def prepare(self, camera: Camera) -> None:
        """Called on onboarding / update: resolve URIs, register with the gateway, etc."""

    async def teardown(self, camera: Camera) -> None:
        """Called when a camera is disabled or deleted."""

    @abstractmethod
    async def probe(self, camera: Camera) -> ProbeResult:
        """Actively check source health."""

    @abstractmethod
    def playback(self, camera: Camera, token: str, expires_at: datetime) -> PlaybackInfo:
        """How a browser should render this camera (never includes source credentials)."""
