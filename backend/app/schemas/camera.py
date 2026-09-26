from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.netguard import check_url_static
from app.models.enums import CameraStatus, CameraType, HealthMode, OnboardingSource, SourceProtocol
from app.schemas import ORMModel

ALLOWED_SCHEMES = {
    SourceProtocol.RTSP: {"rtsp", "rtsps"},
    SourceProtocol.ONVIF: {"http", "https"},
    SourceProtocol.HLS: {"http", "https"},
    SourceProtocol.VENDOR_API: {"http", "https"},
}


def check_endpoint(v: str) -> str:
    parts = urlsplit(v)
    if parts.username or parts.password:
        raise ValueError("Do not embed credentials in stream_endpoint; use stream_username / stream_password")
    if not parts.scheme or not parts.hostname:
        raise ValueError("stream_endpoint must be an absolute URL")
    check_url_static(v)  # UnsafeTarget is a ValueError -> 422
    return v


def check_scheme(protocol: SourceProtocol, endpoint: str) -> None:
    scheme = urlsplit(endpoint).scheme.lower()
    allowed = ALLOWED_SCHEMES[protocol]
    if scheme not in allowed:
        raise ValueError(f"{protocol} endpoints must use one of {sorted(allowed)}")


class CameraBase(BaseModel):
    name: str = Field(min_length=2, max_length=128)
    department_id: int | None = None
    zone: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    camera_type: CameraType = CameraType.FIXED
    source_protocol: SourceProtocol
    stream_endpoint: str = Field(min_length=8, max_length=512)
    vendor: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=64)
    resolution: str | None = Field(default=None, pattern=r"^\d{3,4}x\d{3,4}$")
    fps: int | None = Field(default=None, ge=1, le=120)
    recording_enabled: bool = False
    storage_tier: str | None = Field(default="HOT", pattern=r"^(HOT|WARM|COLD)$")
    storage_location: str | None = Field(default=None, max_length=255)
    retention_days: int = Field(default=30, ge=1, le=3650)
    health_mode: HealthMode = HealthMode.PROBE
    tags: list[str] | None = Field(default=None, max_length=20)

    _endpoint = field_validator("stream_endpoint")(check_endpoint)

    @model_validator(mode="after")
    def scheme_matches_protocol(self):
        check_scheme(self.source_protocol, self.stream_endpoint)
        return self


class CameraCreate(CameraBase):
    id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{1,31}$", description="Camera ID, e.g. C001")
    stream_username: str | None = Field(default=None, max_length=128)
    stream_password: str | None = Field(default=None, max_length=256, description="Stored encrypted, never returned")


class CameraUpdate(BaseModel):
    """Partial update; same limits as creation. Protocol and ID are immutable."""

    name: str | None = Field(default=None, min_length=2, max_length=128)
    department_id: int | None = None
    zone: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    camera_type: CameraType | None = None
    stream_endpoint: str | None = Field(default=None, min_length=8, max_length=512)
    stream_username: str | None = Field(default=None, max_length=128)
    stream_password: str | None = Field(default=None, max_length=256)
    vendor: str | None = Field(default=None, max_length=64)
    model: str | None = Field(default=None, max_length=64)
    resolution: str | None = Field(default=None, pattern=r"^\d{3,4}x\d{3,4}$")
    fps: int | None = Field(default=None, ge=1, le=120)
    recording_enabled: bool | None = None
    storage_tier: str | None = Field(default=None, pattern=r"^(HOT|WARM|COLD)$")
    storage_location: str | None = Field(default=None, max_length=255)
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    health_mode: HealthMode | None = None
    is_enabled: bool | None = None
    tags: list[str] | None = Field(default=None, max_length=20)

    @field_validator("stream_endpoint")
    @classmethod
    def _endpoint(cls, v: str | None) -> str | None:
        return check_endpoint(v) if v is not None else v


class DepartmentOut(ORMModel):
    id: int
    code: str
    name: str


class CameraOut(ORMModel):
    id: str
    name: str
    department_id: int | None
    department: DepartmentOut | None
    zone: str | None
    address: str | None
    latitude: float
    longitude: float
    camera_type: CameraType
    source_protocol: SourceProtocol
    stream_endpoint: str
    stream_username: str | None
    has_credentials: bool = False
    gateway_path: str | None
    vendor: str | None
    model: str | None
    resolution: str | None
    fps: int | None
    recording_enabled: bool
    storage_tier: str | None
    storage_location: str | None
    retention_days: int
    health_mode: HealthMode
    status: CameraStatus
    status_reason: str | None
    status_changed_at: datetime | None
    last_heartbeat_at: datetime | None
    speed_kmh: float | None = None
    heading_deg: float | None = None
    location_updated_at: datetime | None = None
    health_metrics: dict | None
    is_enabled: bool
    onboarding_source: OnboardingSource
    tags: list[str] | None
    open_alerts: int = 0
    created_at: datetime
    updated_at: datetime


class CameraBulkCreate(BaseModel):
    cameras: list[CameraCreate] = Field(min_length=1, max_length=500)


class BulkResult(BaseModel):
    created: list[str]
    errors: dict[str, str]


class HeartbeatIn(BaseModel):
    # GPS telemetry from mobile cameras (dashcams); fixed cameras omit these
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    speed_kmh: float | None = Field(default=None, ge=0, le=300)
    heading_deg: float | None = Field(default=None, ge=0, lt=360)
    fps: float | None = Field(default=None, ge=0, le=240)
    bitrate_kbps: float | None = Field(default=None, ge=0)
    packet_loss_pct: float | None = Field(default=None, ge=0, le=100)
    uptime_s: int | None = Field(default=None, ge=0)
    temperature_c: float | None = None
    firmware: str | None = Field(default=None, max_length=64)


class PlaybackInfo(BaseModel):
    camera_id: str
    kind: str  # "hls" | "snapshot" | "clip" | "unavailable"
    url: str | None
    webrtc_url: str | None = None
    token: str | None = None
    expires_at: datetime | None = None
    note: str | None = None


class TrackPoint(BaseModel):
    t: datetime
    latitude: float
    longitude: float
    speed_kmh: float | None
    heading_deg: float | None


class RecordingSegment(BaseModel):
    start: datetime
    duration: float


class OnvifDiscoverIn(BaseModel):
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=256)


class OnvifDiscoveredDevice(BaseModel):
    device_service_url: str
    manufacturer: str | None
    model: str | None
    firmware: str | None
    serial: str | None
    hardware_id: str | None
    stream_uri: str | None
    already_registered: bool = False
