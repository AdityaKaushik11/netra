# API reference

Interactive OpenAPI/Swagger: **`https://localhost:8443/api/docs`** (ReDoc at `/api/redoc`, raw spec at
`/api/openapi.json`). This page summarises the contract and the main workflows.

Base path: `/api/v1`. All bodies are JSON. Errors: `{"detail": "..."}` (422 returns field-level detail).

## Authentication

| Caller | How |
|---|---|
| Operators / admins | `POST /auth/login {username, password}` → `access_token` (JWT, 8 h). Send `Authorization: Bearer <token>`. |
| Machines (AI engines, edge agents, partner VMS) | `X-API-Key: ntr_…` issued by an admin via `POST /api-clients`. Scopes: `events:write`, `cameras:heartbeat`, `cameras:write`. |

Roles: **ADMIN** (everything), **OPERATOR** (alerts, watchlist, probes), **VIEWER** (read-only).

## Endpoints

| Method & path | Auth | Purpose |
|---|---|---|
| `POST /auth/login` · `POST /auth/token` | — | JWT login (JSON / OAuth2 form for Swagger) |
| `GET /auth/me` | any | Current user |
| `GET /users` · `POST /users` | admin | User management |
| `GET/POST /api-clients` · `POST /api-clients/{id}/revoke` | admin | Machine API keys (shown once) |
| `GET /departments` | any | Departments |
| **Cameras** | | |
| `GET /cameras?q&status&department_id&zone&protocol&camera_type&enabled&limit&offset` | any | Search / filter registry |
| `GET /cameras/zones` | any | Distinct zones |
| `POST /cameras` | admin JWT **or** key `cameras:write` | Onboard (manual or API) |
| `POST /cameras/bulk` | admin / `cameras:write` | Bulk onboarding (≤ 500) with per-item errors |
| `GET /cameras/{id}` · `PATCH /cameras/{id}` | any · admin | Read / edit / enable / disable |
| `GET /cameras/{id}/audit` | any | Audit history of the camera |
| `POST /cameras/{id}/heartbeat` | `cameras:heartbeat` | Edge / dashcam heartbeat with metrics and optional GPS (`latitude`, `longitude`, `speed_kmh`, `heading_deg`) |
| `GET /cameras/{id}/track?minutes=` | any | GPS track of a mobile camera |
| `GET /cameras/{id}/recordings` | any | Recorded segments on the gateway |
| `GET /cameras/{id}/clip?start&duration` | any | Recorded MP4 clip descriptor + stream token (audited) |
| `POST /cameras/{id}/probe` | operator | Probe health now |
| `GET /cameras/{id}/playback` | any | Live-view descriptor + 5-min camera-scoped stream token |
| `GET /cameras/{id}/snapshot?token=` | stream token | Vendor-API snapshot proxy |
| `POST /onvif/discover {username, password}` | admin | Probe ONVIF targets, resolve stream URIs (credentials in the body, never the URL) |
| **Analytics events** | | |
| `POST /events` | `events:write` / admin | Ingest one inference result |
| `POST /events/batch` | `events:write` / admin | Ingest ≤ 500 (edge store-and-forward) |
| `GET /events?camera_id&event_type&identifier&since&until&watchlist_hit&min_confidence` | any | Event history |
| `GET /events/{id}` | any | One event |
| `GET /events/export.csv?…` | operator | CSV report |
| **Search & trace** | | |
| `GET /search?q=` | any | Entities, watchlist and cameras containing `q` |
| `GET /trace/{identifier}?since&until` | any | Chronological movement history + anomalies |
| **Watchlist** | | |
| `GET /watchlist?q&category&entity_type&active` | any | List with hit counts / last seen |
| `POST /watchlist` · `PATCH /watchlist/{id}` · `DELETE /watchlist/{id}` | operator | Manage (delete = deactivate) |
| **Alerts** | | |
| `GET /alerts?status&severity&camera_id&identifier&since` | any | Alert queue (repeat `status`) |
| `GET /alerts/{id}` | any | Detail |
| `POST /alerts/{id}/acknowledge {note?}` | operator | NEW → ACKNOWLEDGED |
| `POST /alerts/{id}/resolve {note, false_positive}` | operator | → RESOLVED / FALSE_POSITIVE |
| `POST /alerts/bulk {action, ids \| older_than_minutes, note}` | operator | Bulk acknowledge / resolve (each change audited) |
| **Stats & system** | | |
| `GET /stats/overview` · `GET /stats/timeseries?hours=` | any | Dashboard KPIs, hourly series |
| `GET /audit?entity_type&action&actor` | admin | Audit log |
| `GET /api/health` · `GET /api/ready` | — | Liveness / readiness |
| `WS /ws?token=<jwt>` | any | Real-time channel |

## Detection event contract

```json
POST /api/v1/events
X-API-Key: ntr_...

{
  "event_id": "edge-ahm-042-000187",      // optional, strongly recommended: makes retries idempotent
  "camera_id": "C001",
  "event_type": "ANPR",                   // ANPR | VEHICLE_DETECTION | PERSON_DETECTION | FACE_RECOGNITION | OBJECT_DETECTION
                                          // dashcam ADAS: OVERSPEED | HARSH_BRAKING | COLLISION_WARNING | DRIVER_DROWSINESS
  "timestamp": "2026-09-25T10:02:11+05:30", // timezone required
  "vehicle_number": "GJ01XX0001",         // required for ANPR (alias: "plate")
  "confidence": 0.94,                     // 0..1
  "vehicle_type": "car",
  "vehicle_color": "white",
  "bounding_box": {"x": 412, "y": 388, "w": 176, "h": 44},
  "snapshot_url": "https://edge-042/snap/000187.jpg",
  "model_name": "anpr-yolov8n+paddleocr-v4",
  "attributes": {"lane": 2},
  "latitude": 23.0412, "longitude": 72.5451, "speed_kmh": 38  // optional: capture position of mobile cameras
}
```

Responses:

| Status | `status` field | Meaning |
|---|---|---|
| 201 | `created` | Stored; `alert_ids` lists alerts raised/updated |
| 200 | `duplicate` | Same `event_id` already stored (safe retry) |
| 200 | `suppressed` | Repeat read inside the dedup window; folded into `event_id` |
| 404 / 409 / 422 | — | Unknown or disabled camera, invalid payload, clock skew / too old |

Message-channel alternative: `XADD netra:ingest:detections * payload '<same JSON>' client '<name>'`.

## Real-time messages (`/api/v1/ws`)

```json
{"type": "alert.created", "ts": "2026-09-25T04:41:03.120Z", "data": { ...Alert }}
```

| type | data |
|---|---|
| `detection.created` | DetectionEvent |
| `alert.created` / `alert.updated` | Alert |
| `camera.status` | Camera (status changed) |
| `camera.created` / `camera.updated` / `camera.bulk_created` | Camera / `{ids}` |
| `camera.location` | `{id, latitude, longitude, speed_kmh, heading_deg, at}` (dashcam GPS fix) |
| `watchlist.changed` | `{id, action}` |

Send `ping` every ≤ 60 s to keep the socket alive (the console does this automatically).

## Example workflow with curl

```bash
BASE=https://localhost:8443/api/v1
TOKEN=$(curl -sk $BASE/auth/login -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PASSWORD\"}" | jq -r .access_token)

# 1. onboard a camera
curl -sk $BASE/cameras -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{
  "id":"C010","name":"Test Junction","latitude":23.03,"longitude":72.58,"camera_type":"ANPR",
  "source_protocol":"HLS","stream_endpoint":"https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8"}'

# 2. post a detection as the analytics engine
curl -sk $BASE/events -H "X-API-Key: $SEED_API_KEY" -H 'Content-Type: application/json' -d "{
  \"camera_id\":\"C010\",\"event_type\":\"ANPR\",\"timestamp\":\"$(date -u +%FT%TZ)\",
  \"vehicle_number\":\"GJ01XX0001\",\"confidence\":0.95}"

# 3. trace the vehicle
curl -sk $BASE/trace/GJ01XX0001 -H "Authorization: Bearer $TOKEN" | jq '.stops[] | {camera_id, detected_at}'
```
