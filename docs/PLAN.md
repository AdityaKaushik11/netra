# Requirements Traceability — Netra: CCTV Monitoring, Video Analytics & Real-Time Alert Platform

Every requirement in the okDriver brief mapped to the component that implements it.

## 1. Technology choices (aligned with okDriver's stack)

| Layer | Choice | Why |
|---|---|---|
| Backend API | **FastAPI (Python 3.12)**, SQLAlchemy 2 (async), Pydantic v2 | okDriver's stack; auto OpenAPI/Swagger |
| Database | **MySQL 8** (RDS-compatible), Alembic migrations | okDriver uses MySQL/RDS |
| Real-time | **Redis Pub/Sub** fan-out → **WebSocket** to browsers; **Redis Streams** as a message-channel ingest path | Horizontally scalable: any API node can serve any socket |
| Video gateway | **MediaMTX** (RTSP → LL-HLS / WebRTC relay) | Standard RTSP relay used in production VMS setups |
| Camera sources | Simulated IP cameras (RTSP), mock **ONVIF** device, public **HLS** stream, simulated **vendor NVR API** (snapshots), simulated **dashcam** on a patrol van (RTSP + GPS) | Five logically different source types behind one adapter interface |
| AI events | Analytics simulator posting ANPR / vehicle / person events (HTTP or Redis Stream) | Brief says no model training needed |
| Frontend | **React + TypeScript + Vite**, Tailwind, TanStack Query, **Leaflet**, hls.js | Professional SPA, operator-console UI |
| Edge/TLS | **Caddy** reverse proxy with HTTPS | TLS for exposed services, single origin |
| Deployment | **Docker Compose**, GitHub Actions CI | One-command setup |
| Observability | Prometheus `/metrics`, structured JSON logs, `/health` endpoints | Production thinking |

## 2. Requirement → implementation map

| # | Requirement | Implementation |
|---|---|---|
| 3 | Camera registry: add/edit/disable/search/filter; all metadata fields | `cameras` table + `/api/v1/cameras` CRUD, filters (status, dept, zone, protocol, type, text) |
| 3 | Manual + API onboarding | UI form (manual) + `POST /api/v1/cameras` & `POST /api/v1/cameras/bulk` via API key; ONVIF discovery onboarding |
| 3 | Online/Offline/Degraded health | Health-monitor worker (probes gateway / HLS / vendor API / heartbeats), leader-elected via Redis lock |
| 3 | Audit history | `audit_logs` table; per-camera history tab |
| 3 | Map of cameras | Leaflet map, markers coloured by status, pulsing when an alert is open |
| 4 | ≥2 different live sources + adapter for RTSP/ONVIF/vendor | `adapters/` package: `RtspAdapter`, `OnvifAdapter`, `HlsAdapter`, `VendorApiAdapter` behind `CameraAdapter` interface |
| 5 | Operational dashboard (grid, counts, alerts, detections, search, history, severity, health, stats) | Dashboard page: KPI strip, live map, alert feed, detection stream, camera grid, charts |
| 6 | GIS + movement history | Trace page: plate search → chronological timeline + numbered route polyline on map |
| 7 | AI inference ingest (ANPR etc.), validate, store, correlate, push | `/api/v1/events` (+batch) and Redis Stream consumer → ingestion pipeline |
| 8 | Watchlist CRUD, matching, alerts, ack/resolve | `watchlist_entries`, exact + fuzzy (edit-distance 1) plate match, `alerts` with NEW→ACKNOWLEDGED→RESOLVED |
| 9 | Real-time sync, persistence, duplicate prevention | WebSocket push; idempotency key (`event_uid` unique); Redis temporal dedup window; alert cool-down (hit counter instead of new alert) |
| 12 | Scalability note | `docs/SCALABILITY.md` — edge/regional/central, GPU sizing, bandwidth, storage tiers, HA/DR, security, cost |
| 13 | Security | JWT auth + RBAC (ADMIN/OPERATOR/VIEWER), hashed API keys for devices, Fernet-encrypted stream credentials never sent to browser, short-lived signed stream tokens verified by the video gateway, HTTPS, rate limiting, audit logs, env-based config, no secrets in git |
| 14 | Deliverables | README, architecture diagram, ER diagram, API docs (Swagger + `docs/API.md`), watchlist dataset, demo script, submission note |
| 4/8 | Recorded feed, evidence for alerts | Gateway recording + playback server; camera replay; 40 s evidence clip in every alert on a recorded camera |
| — | okDriver dashcam | Mobile camera D001: GPS telemetry & track, geotagged ANPR, ADAS events (overspeed, harsh braking, collision warning, drowsiness) |
| 18 | Optional extras | ONVIF mock, RTSP→HLS gateway, ANPR dedup, heartbeat service, RBAC views, route reconstruction, Docker Compose, tests + CI, Prometheus metrics, Redis event architecture |

## 3. Demo scenario (for the 3–5 min video)

1. Log in as admin → dashboard shows 7 cameras across Ahmedabad/Gandhinagar, including a moving patrol-van dashcam.
2. Onboard a new camera (manual form) and via ONVIF discovery → appears on map and grid.
3. Open live feeds (gateway LL-HLS or WebRTC, direct HLS, vendor snapshots, the moving dashcam) and replay recorded footage.
4. Run `make scenario` → `GJ01XX0001` (stolen, CRITICAL) detected at C001 10:02, C002 10:18, C005 10:41.
5. Alerts pop up in real time with sound; acknowledge + resolve.
6. Search `GJ01XX0001` → timeline + route on the map.
7. Stop a camera's stream → marker turns Offline live.
8. Show Swagger `POST /api/v1/events` workflow, then architecture + scalability doc.
