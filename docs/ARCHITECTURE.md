# Netra — Architecture

## 1. System overview

```mermaid
flowchart LR
  subgraph SRC["Camera sources (heterogeneous)"]
    RTSP["IP cameras<br/>RTSP (C001, C002, C006)"]
    ONVIF["ONVIF Profile S device<br/>(C003)"]
    HLS["Existing VMS / portal<br/>HLS (C004)"]
    VENDOR["Vendor NVR cloud API<br/>REST + snapshots (C005)"]
    DASH["okDriver dashcam (D001)<br/>RTSP over 4G + GPS"]
  end

  subgraph EDGE["Edge / analytics"]
    AI["AI inference engine<br/>(ANPR, person, object)"]
    AGENT["Edge agent<br/>heartbeats"]
  end

  subgraph CORE["Netra platform"]
    GW["Video gateway<br/>MediaMTX<br/>RTSP → LL-HLS / WebRTC<br/>recording + playback"]
    API["FastAPI API replicas<br/>REST + WebSocket"]
    ING["Ingestion pipeline<br/>validate → idempotency → dedup<br/>→ store → correlate → alert"]
    HM["Health monitor<br/>(leader-elected)"]
    AD["Source adapters<br/>RTSP · ONVIF · HLS · Vendor"]
    WL["Watchlist matcher<br/>exact + fuzzy index"]
    REDIS[("Redis<br/>Pub/Sub · Streams<br/>dedup keys · rate limits")]
    DB[("MySQL 8<br/>cameras · events · alerts<br/>watchlist · audit")]
  end

  subgraph UI["Operators"]
    CADDY["Caddy HTTPS edge"]
    SPA["React console<br/>dashboard · map · live wall<br/>alerts · trace · watchlist"]
  end

  RTSP -- RTSP pull (creds server-side) --> GW
  DASH -- RTSP --> GW
  DASH -- "GPS heartbeats, ANPR + ADAS events" --> API
  ONVIF -- SOAP GetStreamUri --> AD
  ONVIF -- RTSP --> GW
  HLS -- manifest probe --> AD
  VENDOR -- status / snapshot (API key) --> AD
  AD --> GW
  AI -- "REST /events (X-API-Key)" --> API
  AI -- "XADD netra:ingest:detections" --> REDIS
  AGENT -- "/cameras/{id}/heartbeat" --> API
  API --> ING --> WL
  ING --> DB
  REDIS -- consumer group --> ING
  ING -- publish --> REDIS
  HM --> AD
  HM --> DB
  HM -- camera.status --> REDIS
  REDIS -- fan-out --> API
  GW -- "auth hook (stream token)" --> API
  SPA <--> CADDY
  CADDY -- "/api, WebSocket" --> API
  CADDY -- "/media (LL-HLS)" --> GW
```

**Networks** (docker-compose mirrors production segmentation):

| Network | Members | Purpose |
|---|---|---|
| `cameras` | gateway, backend (probes), camera simulators | Camera VLAN analogue. Never reachable from browsers. |
| `app` | Caddy, backend, gateway | Application tier. |
| `data` | backend, MySQL, Redis, simulator (stream producer) | Data tier. No published ports. |

Only Caddy (HTTPS 8443) and the gateway's WebRTC UDP port are published; the API port is bound to `127.0.0.1` for local debugging.

## 2. Components

| Component | Responsibility | Code |
|---|---|---|
| Source adapters | One interface (`prepare`, `probe`, `playback`, `teardown`) hides RTSP / ONVIF / HLS / vendor-API differences. Adding a vendor SDK = one class. | `backend/app/adapters/` |
| Video gateway | Pulls RTSP on the camera network, remuxes to LL-HLS (≈1–2 s latency) and WebRTC/WHEP (sub-second), records fMP4 segments (6 h hot tier) and serves any time window as MP4 through its playback server. Paths registered dynamically through its control API; every viewer (live or recorded) authorised by the backend. | `infra/gateway/mediamtx.yml`, `backend/app/services/gateway.py` |
| Ingestion pipeline | Validates, deduplicates, persists and correlates analytics events; raises alerts; publishes real-time messages after commit. Shared by REST, batch and stream inputs. | `backend/app/services/ingestion.py` |
| Watchlist matcher | In-memory exact index + SymSpell-style deletion index for edit-distance-1 (OCR error) matches in O(len). Version counter in Redis keeps replicas coherent. | `backend/app/services/watchlist_matcher.py` |
| Stream consumer | Redis Streams consumer group (at-least-once, ACK after commit, dead-letter stream, reclaim of stale pending messages). | `backend/app/services/stream_consumer.py` |
| Event bus | Publish to one Redis Pub/Sub channel, every replica fans out to its own WebSockets → no sticky sessions required. | `backend/app/services/event_bus.py` |
| Health monitor | Probes each enabled camera (gateway path readiness + inbound bitrate, HLS manifest latency, vendor status API) or evaluates heartbeat age; hysteresis against flapping; one leader via Redis lock. | `backend/app/services/health_monitor.py` |
| Mobile cameras | Dashcams send GPS in heartbeats → `cameras.latitude/longitude/speed/heading` + `camera_positions` track; events carry their own capture position so alerts are geolocated on the move. | `backend/app/api/routes/cameras.py`, `simulator/sim/dashcam.py` |
| Console | React SPA: dashboard, map, live wall, registry, alerts, detections, trace, watchlist, audit, API clients. | `frontend/src/` |

## 3. Detection → alert sequence

```mermaid
sequenceDiagram
  autonumber
  participant AI as AI engine (edge)
  participant API as Netra API
  participant R as Redis
  participant DB as MySQL
  participant UI as Operator console

  AI->>API: POST /api/v1/events {event_id, camera_id, vehicle_number, confidence, bbox…}
  API->>API: Pydantic + semantic validation (camera enabled, clock skew, plate format)
  API->>DB: event_id already stored? → 200 duplicate (idempotent retry)
  API->>R: SET NX dedup:{cam}:{type}:{plate} EX 60
  alt key held (repeat read)
    API->>DB: repeat_count += 1 on original event
    API-->>AI: 200 suppressed
  else first read
    API->>DB: INSERT detection_event (location snapshot)
    API->>API: watchlist match (exact / fuzzy, confidence ≥ 0.60)
    opt match
      API->>DB: open alert same entity+camera within cool-down? → hit_count++ : INSERT alert + audit
    end
    API->>DB: COMMIT
    API->>R: PUBLISH detection.created / alert.created
    R-->>API: fan-out to every replica
    API-->>UI: WebSocket push → toast + sound, map marker pulses, feeds update
    API-->>AI: 201 created {event_id, alert_ids}
  end
```

### Duplicate & storm control (brief §9 "prevent duplicate or uncontrolled event generation")

| Layer | Mechanism | Effect |
|---|---|---|
| Transport retries | `event_id` unique constraint | A retried POST / re-delivered stream message never creates a second row |
| Sensor repeats | Redis `SET NX EX` per camera+type+identity (60 s) | 10 ANPR reads of one passing car → 1 event with `repeat_count = 9` |
| Alert storms | Open alert per watchlist-entry + camera within 5-min cool-down is updated (`hit_count`) instead of re-raised | Operators see one actionable alert, not dozens |
| Low-quality reads | `MIN_MATCH_CONFIDENCE` (0.60); fuzzy matches downgraded one severity level | Fewer false positives |
| Abuse | Per-API-key / per-user / per-IP rate limits in Redis | Bounded ingest from any single producer |

## 4. Live video path & stream security

```mermaid
sequenceDiagram
  participant B as Browser (hls.js)
  participant API as Netra API
  participant C as Caddy
  participant G as Video gateway
  participant Cam as Camera (RTSP, auth)

  B->>API: GET /cameras/C001/playback (JWT)
  API->>API: audit STREAM_ACCESSED, sign 5-min token {cam: C001}
  API-->>B: {kind: hls, url: /media/cam-c001/index.m3u8, token}
  B->>C: GET /media/cam-c001/index.m3u8?token=…
  C->>G: proxy
  G->>API: POST /internal/media-auth {path, query}
  API-->>G: 200 if token valid and scoped to this path
  G->>Cam: RTSP pull with credentials (decrypted server-side, never sent to browser)
  G-->>B: LL-HLS playlist / parts
```

* Credentials are stored **Fernet-encrypted** (`stream_secret_enc`) and the API refuses endpoints with inline `user:pass@`.
* Browsers only ever see the gateway path and a camera-scoped, short-lived token.
* Vendor-API snapshots go through `/cameras/{id}/snapshot?token=` so the vendor key stays server-side.
* `/api/v1/internal/*` and `/api/metrics` are blocked at the edge proxy.

## 5. Data model (ER diagram)

```mermaid
erDiagram
  DEPARTMENTS ||--o{ CAMERAS : owns
  DEPARTMENTS ||--o{ USERS : employs
  CAMERAS ||--o{ DETECTION_EVENTS : produces
  CAMERAS ||--o{ ALERTS : "raised at"
  CAMERAS ||--o{ CAMERA_POSITIONS : "GPS track"
  DETECTION_EVENTS ||--o{ ALERTS : triggers
  WATCHLIST_ENTRIES ||--o{ ALERTS : matched
  USERS ||--o{ ALERTS : "ack / resolve"
  USERS ||--o{ WATCHLIST_ENTRIES : creates

  CAMERAS {
    varchar id PK "C001"
    varchar name
    int department_id FK
    varchar zone
    decimal latitude
    decimal longitude
    enum camera_type
    enum source_protocol "RTSP|ONVIF|HLS|VENDOR_API"
    varchar stream_endpoint "no credentials"
    varchar stream_username
    text stream_secret_enc "Fernet"
    varchar resolved_stream_uri
    varchar gateway_path
    enum health_mode "PROBE|HEARTBEAT"
    enum status "ONLINE|DEGRADED|OFFLINE|UNKNOWN"
    datetime last_heartbeat_at
    json health_metrics
    bool recording_enabled
    varchar storage_tier "HOT|WARM|COLD"
    int retention_days
    bool is_enabled
    enum onboarding_source
  }
  CAMERA_POSITIONS {
    bigint id PK
    varchar camera_id FK
    datetime recorded_at
    decimal latitude
    decimal longitude
    float speed_kmh
    float heading_deg
  }
  DETECTION_EVENTS {
    bigint id PK
    varchar event_uid UK "idempotency key"
    varchar camera_id FK
    enum event_type
    datetime detected_at
    varchar identifier_normalized "indexed"
    float confidence
    json bounding_box
    decimal latitude "snapshot"
    decimal longitude "snapshot"
    int repeat_count
    bool watchlist_hit
  }
  WATCHLIST_ENTRIES {
    int id PK
    enum entity_type "VEHICLE|PERSON"
    varchar identifier_normalized "UK with entity_type"
    enum category
    enum severity
    varchar case_reference
    bool is_active
    datetime valid_until
  }
  ALERTS {
    int id PK
    bigint event_id FK
    int watchlist_entry_id FK
    varchar camera_id FK
    enum match_type "EXACT|FUZZY"
    enum severity
    enum status "NEW|ACKNOWLEDGED|RESOLVED|FALSE_POSITIVE"
    int hit_count
    datetime last_hit_at
    text resolution_note
  }
  USERS {
    int id PK
    varchar username UK
    varchar password_hash "bcrypt"
    enum role "ADMIN|OPERATOR|VIEWER"
  }
  API_CLIENTS {
    int id PK
    varchar key_hash UK "HMAC-SHA256"
    json scopes
  }
  AUDIT_LOGS {
    bigint id PK
    datetime created_at
    enum actor_type
    varchar action
    varchar entity_type
    varchar entity_id
    json details
    varchar ip_address
  }
```

### Indexes (all created by the Alembic migration)

| Table | Index | Serves |
|---|---|---|
| detection_events | `(identifier_normalized, detected_at)` | Entity search & movement trace |
| detection_events | `(camera_id, detected_at)` | Per-camera history |
| detection_events | `(event_type, detected_at)`, `(detected_at)` | Filtered history, time-series |
| detection_events | `UNIQUE(event_uid)` | Idempotency |
| alerts | `(status, triggered_at)` | Open-alert queue |
| alerts | `(watchlist_entry_id, camera_id, last_hit_at)` | Cool-down lookup on the hot path |
| cameras | `(status)`, `(department_id, zone)`, `(source_protocol)`, `(latitude, longitude)` | Registry filters, map |
| camera_positions | `(camera_id, recorded_at)` | Dashcam track queries |
| watchlist_entries | `UNIQUE(entity_type, identifier_normalized)` | No duplicate records |
| audit_logs | `(entity_type, entity_id, created_at)` | Per-camera audit history |

Timestamps are stored as UTC `DATETIME(6)`; the ORM always returns timezone-aware values.
The schema is portable to Amazon RDS / Aurora MySQL with no changes.

## 6. Security controls

| Requirement (brief §13) | Implementation |
|---|---|
| Authentication & RBAC | JWT (HS256, 8 h) for people; ADMIN / OPERATOR / VIEWER enforced per route. Hashed, scoped API keys for machines (`events:write`, `cameras:heartbeat`, `cameras:write`). |
| Input validation | Pydantic v2 schemas (coordinates, URL schemes per protocol, plate format, bbox, timezone-aware timestamps, payload size) + semantic checks (camera enabled, clock skew, event age). |
| Secure stream URLs & credentials | Fernet encryption at rest, never serialised, inline credentials rejected, gateway injects them server-side, camera-scoped 5-min stream tokens. |
| HTTPS/TLS | Caddy terminates TLS (internal CA locally, automatic ACME in production), HSTS and security headers. |
| Audit logs | Logins (success/failure with IP), onboarding, edits (field-level diffs, secrets masked), enable/disable, status changes, stream access, alert raise/ack/resolve, watchlist changes, API-key issue/revoke. |
| Rate limiting | Redis fixed-window: login per IP, API per user, ingest per API key. |
| No secrets in Git | `.env` git-ignored; `make env` generates random secrets; seed reads everything from env. |
| Environment config | `pydantic-settings`; every tunable documented in `.env.example`. |
| Other | bcrypt (cost 12) with timing equaliser; account lockout; server-side token revocation; SSRF guard on every outbound camera request; strict CSP; least-privilege containers; internal endpoints blocked at the edge; generic 500 responses. Full list: [SECURITY.md](SECURITY.md). |
