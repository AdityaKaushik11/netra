from app.models import Alert, Camera, DetectionEvent
from app.schemas.alert import AlertOut
from app.schemas.camera import CameraOut
from app.schemas.event import DetectionEventOut


def event_out(e: DetectionEvent) -> DetectionEventOut:
    out = DetectionEventOut.model_validate(e)
    out.camera_name = e.camera.name if e.camera else None
    return out


def alert_out(a: Alert) -> AlertOut:
    out = AlertOut.model_validate(a)
    if a.camera:
        out.camera_name = a.camera.name
        out.camera_zone = a.camera.zone
    if a.watchlist_entry:
        out.category = a.watchlist_entry.category
        out.watchlist_description = a.watchlist_entry.description
        out.watchlist_identifier = a.watchlist_entry.identifier
        out.watchlist_attributes = a.watchlist_entry.attributes
        out.source_agency = a.watchlist_entry.source_agency
        out.case_reference = a.watchlist_entry.case_reference
    if a.event:
        out.snapshot_url = a.event.snapshot_url
        out.vehicle_type = a.event.vehicle_type
        out.vehicle_color = a.event.vehicle_color
    return out


def camera_out(c: Camera, open_alerts: int = 0) -> CameraOut:
    out = CameraOut.model_validate(c)
    out.has_credentials = bool(c.stream_secret_enc)
    out.open_alerts = open_alerts
    return out
