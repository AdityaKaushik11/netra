from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


class CameraStatus(StrEnum):
    ONLINE = "ONLINE"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class CameraType(StrEnum):
    FIXED = "FIXED"
    PTZ = "PTZ"
    ANPR = "ANPR"
    DOME = "DOME"
    BULLET = "BULLET"
    THERMAL = "THERMAL"
    DASHCAM = "DASHCAM"  # vehicle-mounted mobile camera (okDriver dashcam / PCR van)


class SourceProtocol(StrEnum):
    RTSP = "RTSP"  # pulled by the video gateway, relayed as LL-HLS / WebRTC
    ONVIF = "ONVIF"  # stream URI resolved via ONVIF Media service, then pulled as RTSP
    HLS = "HLS"  # already-published HLS (e.g. existing VMS / city portal)
    VENDOR_API = "VENDOR_API"  # proprietary NVR/cloud API (snapshot / status endpoints)


class HealthMode(StrEnum):
    PROBE = "PROBE"  # platform actively probes the source
    HEARTBEAT = "HEARTBEAT"  # an edge agent pushes heartbeats


class OnboardingSource(StrEnum):
    MANUAL = "MANUAL"
    API = "API"
    DISCOVERY = "DISCOVERY"
    SEED = "SEED"


class EventType(StrEnum):
    ANPR = "ANPR"
    VEHICLE_DETECTION = "VEHICLE_DETECTION"
    PERSON_DETECTION = "PERSON_DETECTION"
    FACE_RECOGNITION = "FACE_RECOGNITION"
    OBJECT_DETECTION = "OBJECT_DETECTION"
    # Dashcam ADAS / driver-monitoring events
    OVERSPEED = "OVERSPEED"
    HARSH_BRAKING = "HARSH_BRAKING"
    COLLISION_WARNING = "COLLISION_WARNING"
    DRIVER_DROWSINESS = "DRIVER_DROWSINESS"


class EntityType(StrEnum):
    VEHICLE = "VEHICLE"
    PERSON = "PERSON"


class WatchlistCategory(StrEnum):
    STOLEN_VEHICLE = "STOLEN_VEHICLE"
    BLACKLISTED_VEHICLE = "BLACKLISTED_VEHICLE"
    WANTED_PERSON = "WANTED_PERSON"
    MISSING_PERSON = "MISSING_PERSON"
    SUSPICIOUS = "SUSPICIOUS"


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


SEVERITY_ORDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def downgrade(sev: Severity) -> Severity:
    return SEVERITY_ORDER[max(0, SEVERITY_ORDER.index(sev) - 1)]


class AlertStatus(StrEnum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class MatchType(StrEnum):
    EXACT = "EXACT"
    FUZZY = "FUZZY"


class ActorType(StrEnum):
    USER = "USER"
    API_CLIENT = "API_CLIENT"
    SYSTEM = "SYSTEM"
