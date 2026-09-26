from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import (
    ActorType,
    AlertStatus,
    CameraStatus,
    CameraType,
    EntityType,
    EventType,
    HealthMode,
    MatchType,
    OnboardingSource,
    Role,
    Severity,
    SourceProtocol,
    WatchlistCategory,
)
from app.models.types import BigIntPK, UTCDateTime, utcnow


def enum_col(enum_cls, **kw):
    return mapped_column(SAEnum(enum_cls, native_enum=False, length=24, validate_strings=True), **kw)


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(128))
    role: Mapped[Role] = enum_col(Role)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    department: Mapped[Department | None] = relationship(lazy="joined")


class ApiClient(Base):
    """Machine identities (AI inference engines, edge gateways, partner VMS) authenticated by API key."""

    __tablename__ = "api_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    key_prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Camera(Base):
    __tablename__ = "cameras"
    __table_args__ = (
        Index("ix_cameras_status", "status"),
        Index("ix_cameras_dept_zone", "department_id", "zone"),
        Index("ix_cameras_protocol", "source_protocol"),
        Index("ix_cameras_geo", "latitude", "longitude"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. "C001"
    name: Mapped[str] = mapped_column(String(128))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    zone: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Numeric(9, 6, asdecimal=False))
    longitude: Mapped[float] = mapped_column(Numeric(9, 6, asdecimal=False))
    camera_type: Mapped[CameraType] = enum_col(CameraType)
    source_protocol: Mapped[SourceProtocol] = enum_col(SourceProtocol)
    # Non-secret endpoint reference. Credentials are stored separately and encrypted.
    stream_endpoint: Mapped[str] = mapped_column(String(512))
    stream_username: Mapped[str | None] = mapped_column(String(128))
    stream_secret_enc: Mapped[str | None] = mapped_column(Text)
    resolved_stream_uri: Mapped[str | None] = mapped_column(String(512))  # e.g. from ONVIF GetStreamUri
    gateway_path: Mapped[str | None] = mapped_column(String(64))
    vendor: Mapped[str | None] = mapped_column(String(64))
    model: Mapped[str | None] = mapped_column(String(64))
    resolution: Mapped[str | None] = mapped_column(String(16))
    fps: Mapped[int | None] = mapped_column(Integer)
    # Storage metadata
    recording_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    storage_tier: Mapped[str | None] = mapped_column(String(16))  # HOT / WARM / COLD
    storage_location: Mapped[str | None] = mapped_column(String(255))
    retention_days: Mapped[int] = mapped_column(Integer, default=30)
    # Health
    health_mode: Mapped[HealthMode] = enum_col(HealthMode, default=HealthMode.PROBE)
    status: Mapped[CameraStatus] = enum_col(CameraStatus, default=CameraStatus.UNKNOWN)
    status_reason: Mapped[str | None] = mapped_column(String(255))
    status_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Mobile cameras (dashcams): live GPS telemetry; latitude/longitude hold the latest fix
    speed_kmh: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)
    location_updated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    health_metrics: Mapped[dict | None] = mapped_column(JSON)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    onboarding_source: Mapped[OnboardingSource] = enum_col(OnboardingSource, default=OnboardingSource.MANUAL)
    tags: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    department: Mapped[Department | None] = relationship(lazy="joined")


class CameraPosition(Base):
    """GPS track of mobile cameras (dashcams). Partition by day / TTL at scale."""

    __tablename__ = "camera_positions"
    __table_args__ = (Index("ix_positions_camera_time", "camera_id", "recorded_at"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"))
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    latitude: Mapped[float] = mapped_column(Numeric(9, 6, asdecimal=False))
    longitude: Mapped[float] = mapped_column(Numeric(9, 6, asdecimal=False))
    speed_kmh: Mapped[float | None] = mapped_column(Float)
    heading_deg: Mapped[float | None] = mapped_column(Float)


class WatchlistEntry(Base):
    __tablename__ = "watchlist_entries"
    __table_args__ = (
        UniqueConstraint("entity_type", "identifier_normalized", name="uq_watchlist_identity"),
        Index("ix_watchlist_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[EntityType] = enum_col(EntityType)
    identifier: Mapped[str] = mapped_column(String(64))  # plate number or person reference id
    identifier_normalized: Mapped[str] = mapped_column(String(64))
    category: Mapped[WatchlistCategory] = enum_col(WatchlistCategory)
    severity: Mapped[Severity] = enum_col(Severity)
    description: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict | None] = mapped_column(JSON)  # make/colour/age etc.
    case_reference: Mapped[str | None] = mapped_column(String(64))  # e.g. FIR number
    source_agency: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    valid_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)


class DetectionEvent(Base):
    """One analytics inference result. High-volume table: partition by month on detected_at at scale."""

    __tablename__ = "detection_events"
    __table_args__ = (
        Index("ix_events_identifier_time", "identifier_normalized", "detected_at"),
        Index("ix_events_camera_time", "camera_id", "detected_at"),
        Index("ix_events_type_time", "event_type", "detected_at"),
        Index("ix_events_detected_at", "detected_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    event_uid: Mapped[str] = mapped_column(String(64), unique=True)  # idempotency key
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"))
    event_type: Mapped[EventType] = enum_col(EventType)
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # Identity of what was seen (plate for vehicles, person ref for face matches)
    identifier: Mapped[str | None] = mapped_column(String(64))
    identifier_normalized: Mapped[str | None] = mapped_column(String(64))
    vehicle_type: Mapped[str | None] = mapped_column(String(32))
    vehicle_color: Mapped[str | None] = mapped_column(String(32))
    object_label: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float)
    bounding_box: Mapped[dict | None] = mapped_column(JSON)
    snapshot_url: Mapped[str | None] = mapped_column(String(512))
    model_name: Mapped[str | None] = mapped_column(String(64))
    source_client: Mapped[str | None] = mapped_column(String(128))
    attributes: Mapped[dict | None] = mapped_column(JSON)
    # Location snapshot at detection time (cameras can be relocated later)
    latitude: Mapped[float] = mapped_column(Numeric(9, 6, asdecimal=False))
    longitude: Mapped[float] = mapped_column(Numeric(9, 6, asdecimal=False))
    # Duplicate suppression: repeated reads within the dedup window increment this instead of new rows
    repeat_count: Mapped[int] = mapped_column(Integer, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    watchlist_hit: Mapped[bool] = mapped_column(Boolean, default=False)

    camera: Mapped[Camera] = relationship(lazy="joined")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_status_time", "status", "triggered_at"),
        Index("ix_alerts_watch_cam_time", "watchlist_entry_id", "camera_id", "last_hit_at"),
        Index("ix_alerts_identifier", "identifier_normalized"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("detection_events.id"))
    watchlist_entry_id: Mapped[int] = mapped_column(ForeignKey("watchlist_entries.id"))
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"))
    identifier: Mapped[str] = mapped_column(String(64))
    identifier_normalized: Mapped[str] = mapped_column(String(64))
    match_type: Mapped[MatchType] = enum_col(MatchType)
    confidence: Mapped[float] = mapped_column(Float)
    severity: Mapped[Severity] = enum_col(Severity)
    status: Mapped[AlertStatus] = enum_col(AlertStatus, default=AlertStatus.NEW)
    title: Mapped[str] = mapped_column(String(255))
    latitude: Mapped[float] = mapped_column(Numeric(9, 6, asdecimal=False))
    longitude: Mapped[float] = mapped_column(Numeric(9, 6, asdecimal=False))
    triggered_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    hit_count: Mapped[int] = mapped_column(Integer, default=1)
    last_hit_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolution_note: Mapped[str | None] = mapped_column(Text)

    camera: Mapped[Camera] = relationship(lazy="joined")
    event: Mapped[DetectionEvent] = relationship(lazy="joined")
    watchlist_entry: Mapped[WatchlistEntry] = relationship(lazy="joined")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    actor_type: Mapped[ActorType] = enum_col(ActorType)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    actor_name: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(45))
