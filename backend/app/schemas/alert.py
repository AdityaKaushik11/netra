from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import AlertStatus, EntityType, MatchType, Severity, WatchlistCategory
from app.schemas import ORMModel


class WatchlistBase(BaseModel):
    entity_type: EntityType = EntityType.VEHICLE
    identifier: str = Field(min_length=3, max_length=64)
    category: WatchlistCategory
    severity: Severity = Severity.HIGH
    description: str | None = Field(default=None, max_length=2000)
    attributes: dict | None = None
    case_reference: str | None = Field(default=None, max_length=64)
    source_agency: str | None = Field(default=None, max_length=128)
    valid_until: datetime | None = None


class WatchlistCreate(WatchlistBase):
    pass


class WatchlistUpdate(BaseModel):
    category: WatchlistCategory | None = None
    severity: Severity | None = None
    description: str | None = None
    attributes: dict | None = None
    case_reference: str | None = None
    source_agency: str | None = None
    valid_until: datetime | None = None
    is_active: bool | None = None


class WatchlistOut(ORMModel):
    id: int
    entity_type: EntityType
    identifier: str
    identifier_normalized: str
    category: WatchlistCategory
    severity: Severity
    description: str | None
    attributes: dict | None
    case_reference: str | None
    source_agency: str | None
    is_active: bool
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime
    hit_count: int = 0
    last_seen_at: datetime | None = None


class AlertOut(ORMModel):
    id: int
    event_id: int
    watchlist_entry_id: int
    camera_id: str
    camera_name: str | None = None
    camera_zone: str | None = None
    identifier: str
    match_type: MatchType
    confidence: float
    severity: Severity
    status: AlertStatus
    title: str
    category: WatchlistCategory | None = None
    watchlist_identifier: str | None = None
    watchlist_description: str | None = None
    watchlist_attributes: dict | None = None
    source_agency: str | None = None
    case_reference: str | None = None
    latitude: float
    longitude: float
    triggered_at: datetime
    hit_count: int
    last_hit_at: datetime
    acknowledged_by: int | None
    acknowledged_at: datetime | None
    resolved_by: int | None
    resolved_at: datetime | None
    resolution_note: str | None
    snapshot_url: str | None = None
    vehicle_type: str | None = None
    vehicle_color: str | None = None


class AlertAction(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class AlertResolve(BaseModel):
    note: str = Field(min_length=3, max_length=2000)
    false_positive: bool = False


class AlertBulkAction(BaseModel):
    action: str = Field(pattern="^(acknowledge|resolve)$")
    ids: list[int] | None = Field(default=None, max_length=1000)
    older_than_minutes: int | None = Field(default=None, ge=1, description="Target all open alerts older than this")
    note: str | None = Field(default=None, max_length=2000)
    false_positive: bool = False


class AlertBulkResult(BaseModel):
    updated: int
