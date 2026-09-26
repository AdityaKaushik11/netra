import re
from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

from app.models.enums import EventType
from app.schemas import ORMModel

_NON_ALNUM = re.compile(r"[^A-Z0-9]")
# Standard Indian registration (e.g. GJ01AB1234) and Bharat series (e.g. 22BH1234AA)
INDIAN_PLATE = re.compile(r"^([A-Z]{2}\d{1,2}[A-Z]{0,3}\d{1,4}|\d{2}BH\d{4}[A-Z]{1,2})$")


def normalize_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    norm = _NON_ALNUM.sub("", value.upper())
    return norm or None


class BoundingBox(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    w: float = Field(gt=0)
    h: float = Field(gt=0)


class DetectionEventIn(BaseModel):
    """Inference result produced by an analytics engine (edge box, GPU worker or vendor VMS)."""

    event_id: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[A-Za-z0-9_.:-]+$",
        description="Producer-side unique id; makes retries idempotent",
    )
    camera_id: str = Field(max_length=32)
    event_type: EventType
    timestamp: datetime = Field(description="Detection time (ISO-8601, timezone required)")
    confidence: float = Field(ge=0, le=1)
    vehicle_number: str | None = Field(
        default=None, max_length=20, validation_alias=AliasChoices("vehicle_number", "plate")
    )
    vehicle_type: str | None = Field(default=None, max_length=32)
    vehicle_color: str | None = Field(default=None, max_length=32)
    person_ref: str | None = Field(default=None, max_length=64, description="Face-recognition gallery id")
    object_label: str | None = Field(default=None, max_length=64)
    # Capture position for mobile cameras (dashcams); fixed cameras use their registered location
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    speed_kmh: float | None = Field(default=None, ge=0, le=300)
    bounding_box: BoundingBox | None = None
    snapshot_url: str | None = Field(default=None, max_length=512)
    model_name: str | None = Field(default=None, max_length=64)
    attributes: dict | None = None

    @field_validator("timestamp")
    @classmethod
    def tz_required(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("timestamp must include a timezone offset")
        return v

    @field_validator("snapshot_url")
    @classmethod
    def safe_snapshot(cls, v: str | None) -> str | None:
        if v and not v.startswith(("http://", "https://", "/")):
            raise ValueError("snapshot_url must be http(s) or a relative path")
        return v

    @model_validator(mode="after")
    def identity_required(self):
        if self.event_type == EventType.ANPR:
            norm = normalize_identifier(self.vehicle_number)
            if not norm or not (4 <= len(norm) <= 12):
                raise ValueError("ANPR events require a vehicle_number of 4-12 alphanumerics")
        if self.event_type == EventType.FACE_RECOGNITION and not self.person_ref:
            raise ValueError("FACE_RECOGNITION events require person_ref")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together")
        if self.attributes and len(str(self.attributes)) > 4000:
            raise ValueError("attributes payload too large")
        return self

    @property
    def identifier(self) -> str | None:
        return self.vehicle_number or self.person_ref


class DetectionBatchIn(BaseModel):
    events: list[DetectionEventIn] = Field(min_length=1, max_length=500)


class IngestResult(BaseModel):
    status: str  # "created" | "duplicate" | "suppressed" | "rejected"
    event_id: int | None = None
    event_uid: str | None = None
    alert_ids: list[int] = []
    detail: str | None = None


class BatchIngestResult(BaseModel):
    results: list[IngestResult]
    created: int
    duplicates: int
    suppressed: int
    rejected: int


class DetectionEventOut(ORMModel):
    id: int
    event_uid: str
    camera_id: str
    camera_name: str | None = None
    event_type: EventType
    detected_at: datetime
    received_at: datetime
    identifier: str | None
    identifier_normalized: str | None
    vehicle_type: str | None
    vehicle_color: str | None
    object_label: str | None
    confidence: float
    bounding_box: dict | None
    snapshot_url: str | None
    model_name: str | None
    source_client: str | None
    attributes: dict | None
    latitude: float
    longitude: float
    repeat_count: int
    last_seen_at: datetime | None
    watchlist_hit: bool


class TraceStop(BaseModel):
    event_id: int
    camera_id: str
    camera_name: str
    zone: str | None
    latitude: float
    longitude: float
    detected_at: datetime
    confidence: float
    repeat_count: int
    minutes_since_previous: float | None
    distance_km_from_previous: float | None
    implied_speed_kmh: float | None


class TraceOut(BaseModel):
    identifier: str
    identifier_normalized: str
    first_seen: datetime | None
    last_seen: datetime | None
    total_detections: int
    distinct_cameras: int
    total_distance_km: float
    watchlist: dict | None
    stops: list[TraceStop]
    anomalies: list[str]
