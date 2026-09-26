export type Role = "ADMIN" | "OPERATOR" | "VIEWER";
export type CameraStatus = "ONLINE" | "DEGRADED" | "OFFLINE" | "UNKNOWN";
export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type AlertStatus = "NEW" | "ACKNOWLEDGED" | "RESOLVED" | "FALSE_POSITIVE";
export type SourceProtocol = "RTSP" | "ONVIF" | "HLS" | "VENDOR_API";
export type CameraType = "FIXED" | "PTZ" | "ANPR" | "DOME" | "BULLET" | "THERMAL" | "DASHCAM";
export type EventType =
  | "ANPR"
  | "VEHICLE_DETECTION"
  | "PERSON_DETECTION"
  | "FACE_RECOGNITION"
  | "OBJECT_DETECTION"
  | "OVERSPEED"
  | "HARSH_BRAKING"
  | "COLLISION_WARNING"
  | "DRIVER_DROWSINESS";

export const ADAS_EVENTS: EventType[] = ["OVERSPEED", "HARSH_BRAKING", "COLLISION_WARNING", "DRIVER_DROWSINESS"];
export type WatchlistCategory =
  | "STOLEN_VEHICLE"
  | "BLACKLISTED_VEHICLE"
  | "WANTED_PERSON"
  | "MISSING_PERSON"
  | "SUSPICIOUS";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  department_id: number | null;
  is_active: boolean;
  last_login_at: string | null;
}

export interface Department {
  id: number;
  code: string;
  name: string;
}

export interface Camera {
  id: string;
  name: string;
  department_id: number | null;
  department: Department | null;
  zone: string | null;
  address: string | null;
  latitude: number;
  longitude: number;
  camera_type: CameraType;
  source_protocol: SourceProtocol;
  stream_endpoint: string;
  stream_username: string | null;
  has_credentials: boolean;
  gateway_path: string | null;
  vendor: string | null;
  model: string | null;
  resolution: string | null;
  fps: number | null;
  recording_enabled: boolean;
  storage_tier: string | null;
  storage_location: string | null;
  retention_days: number;
  health_mode: "PROBE" | "HEARTBEAT";
  status: CameraStatus;
  status_reason: string | null;
  status_changed_at: string | null;
  last_heartbeat_at: string | null;
  speed_kmh: number | null;
  heading_deg: number | null;
  location_updated_at: string | null;
  health_metrics: Record<string, unknown> | null;
  is_enabled: boolean;
  onboarding_source: "MANUAL" | "API" | "DISCOVERY" | "SEED";
  tags: string[] | null;
  open_alerts: number;
  created_at: string;
  updated_at: string;
}

export interface DetectionEvent {
  id: number;
  event_uid: string;
  camera_id: string;
  camera_name: string | null;
  event_type: EventType;
  detected_at: string;
  received_at: string;
  identifier: string | null;
  identifier_normalized: string | null;
  vehicle_type: string | null;
  vehicle_color: string | null;
  object_label: string | null;
  confidence: number;
  bounding_box: { x: number; y: number; w: number; h: number } | null;
  snapshot_url: string | null;
  model_name: string | null;
  source_client: string | null;
  attributes: Record<string, unknown> | null;
  latitude: number;
  longitude: number;
  repeat_count: number;
  last_seen_at: string | null;
  watchlist_hit: boolean;
}

export interface Alert {
  id: number;
  event_id: number;
  watchlist_entry_id: number;
  camera_id: string;
  camera_name: string | null;
  camera_zone: string | null;
  identifier: string;
  match_type: "EXACT" | "FUZZY";
  confidence: number;
  severity: Severity;
  status: AlertStatus;
  title: string;
  category: WatchlistCategory | null;
  watchlist_identifier: string | null;
  watchlist_description: string | null;
  watchlist_attributes: Record<string, unknown> | null;
  source_agency: string | null;
  case_reference: string | null;
  latitude: number;
  longitude: number;
  triggered_at: string;
  hit_count: number;
  last_hit_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  vehicle_type: string | null;
  vehicle_color: string | null;
}

export interface WatchlistEntry {
  id: number;
  entity_type: "VEHICLE" | "PERSON";
  identifier: string;
  identifier_normalized: string;
  category: WatchlistCategory;
  severity: Severity;
  description: string | null;
  attributes: Record<string, unknown> | null;
  case_reference: string | null;
  source_agency: string | null;
  is_active: boolean;
  valid_until: string | null;
  created_at: string;
  hit_count: number;
  last_seen_at: string | null;
}

export interface TrackPoint {
  t: string;
  latitude: number;
  longitude: number;
  speed_kmh: number | null;
  heading_deg: number | null;
}

export interface CameraLocation {
  id: string;
  latitude: number;
  longitude: number;
  speed_kmh: number | null;
  heading_deg: number | null;
  at: string;
}

export interface Overview {
  system: Record<string, string | number>;
  cameras: { online: number; degraded: number; offline: number; unknown: number; disabled: number; total: number };
  alerts: { open: number; new: number; by_severity: Record<Severity, number>; last_24h: number };
  events: { last_5m: number; last_hour: number; last_24h: number; per_minute: number; duplicates_suppressed_24h: number };
  watchlist: { active: number; cached: number };
  top_cameras_24h: { camera_id: string; events: number }[];
  realtime: { ws_clients_this_node: number };
  server_time: string;
}

export interface TimePoint {
  hour: string;
  detections: number;
  watchlist_hits: number;
  alerts: number;
}

export interface TraceStop {
  event_id: number;
  camera_id: string;
  camera_name: string;
  zone: string | null;
  latitude: number;
  longitude: number;
  detected_at: string;
  confidence: number;
  repeat_count: number;
  minutes_since_previous: number | null;
  distance_km_from_previous: number | null;
  implied_speed_kmh: number | null;
}

export interface Trace {
  identifier: string;
  identifier_normalized: string;
  first_seen: string | null;
  last_seen: string | null;
  total_detections: number;
  distinct_cameras: number;
  total_distance_km: number;
  watchlist: {
    id: number;
    category: WatchlistCategory;
    severity: Severity;
    description: string | null;
    case_reference: string | null;
    is_active: boolean;
    alerts: number;
  } | null;
  stops: TraceStop[];
  anomalies: string[];
}

export interface PlaybackInfo {
  camera_id: string;
  kind: "hls" | "snapshot" | "clip" | "unavailable";
  url: string | null;
  webrtc_url: string | null;
  token: string | null;
  expires_at: string | null;
  note: string | null;
}

export interface AuditEntry {
  id: number;
  created_at: string;
  actor_type: "USER" | "API_CLIENT" | "SYSTEM";
  actor_name: string | null;
  action: string;
  entity_type?: string;
  entity_id?: string | null;
  details: Record<string, unknown> | null;
  ip_address?: string | null;
}

export interface RealtimeMessage<T = unknown> {
  type: string;
  ts: string;
  data: T;
}
