# Netra — Integrated CCTV Monitoring, Video Analytics & Real-Time Alert Platform

A working prototype of a centralised CCTV platform: heterogeneous camera sources are onboarded into
one registry, monitored live, enriched with AI analytics events, correlated against a watchlist and
turned into real-time alerts, with GIS movement tracing.

Built for the okDriver Full Stack Developer challenge (aligned with the Gujarat Police Innovation
Hackathon 2026 problem statement).

**Stack:** FastAPI · SQLAlchemy 2 (async) · MySQL 8 · Redis (Pub/Sub, Streams) · WebSocket ·
MediaMTX (RTSP → LL-HLS/WebRTC) · React + TypeScript + Vite · Tailwind · Leaflet · hls.js ·
Caddy (HTTPS) · Docker Compose · Alembic · pytest · GitHub Actions

| | |
|---|---|
| **Architecture document (PDF, for submission)** | [docs/Netra-Architecture.pdf](docs/Netra-Architecture.pdf) |
| **Technical handbook (PDF, 63 pages: every component explained)** | [docs/Netra-Technical-Handbook.pdf](docs/Netra-Technical-Handbook.pdf) |
| Architecture & ER diagram | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Scalability & deployment note (80,000 cameras) | [docs/SCALABILITY.md](docs/SCALABILITY.md) |
| API reference (plus live Swagger at `/api/docs`) | [docs/API.md](docs/API.md) |
| Security controls, verification, ₹0 cost breakdown | [docs/SECURITY.md](docs/SECURITY.md) |
| Deployment: GitHub + Oracle Cloud free VM + Vercel | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| Demo video script | [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) |
| Requirement → implementation map | [docs/PLAN.md](docs/PLAN.md) |
| Watchlist dataset (synthetic) | [backend/app/seed_data/watchlist.json](backend/app/seed_data/watchlist.json) |

---

## What it does

| Brief section | Delivered |
|---|---|
| **3 Camera registry** | Add / edit / disable / search / filter; all metadata incl. storage tier & retention; manual, **API** (`X-API-Key`, bulk) and **ONVIF-discovery** onboarding; Online / Degraded / Offline health; per-camera audit history; map |
| **4 Live video** | Five logically different sources behind one adapter interface: **RTSP** cameras relayed by a video gateway as **LL-HLS or WebRTC**, an **ONVIF** device (SOAP GetStreamUri with WS-Security digest), a direct **HLS** publisher, a **vendor NVR REST API** (snapshots), and a **mobile okDriver-style dashcam** (RTSP over 4G + GPS telemetry). Gateway-relayed cameras are **recorded**; any time window replays as MP4 |
| **5 Dashboard** | KPI strip (online/offline, open alerts by severity, detections, ingest rate, watchlist, suppressed duplicates), live map, active-alert queue with ack, live camera grid, streaming detections, hourly trend, camera-health table, global entity search |
| **6 GIS & movement** | Leaflet map with status-coloured markers that pulse on open alerts; **trace** page with chronological timeline, numbered route, leg distance / time / implied speed, and **impossible-travel (cloned plate) detection** |
| **7 AI analytics** | `POST /events`, `POST /events/batch` and a **Redis Stream** consumer; ANPR, vehicle, person, face and object events; validation and persistence |
| **8 Watchlist & alerts** | Watchlist CRUD (soft delete) for vehicles **and persons** (face-recognition gallery refs); exact + OCR-tolerant **fuzzy** matching; instant alerts with severity, camera, location, confidence, case reference, **live feed and a recorded evidence clip** of the moment; acknowledge / resolve / false-positive with notes, individually or in bulk |
| **9 Real-time** | WebSocket fan-out over Redis Pub/Sub (horizontally scalable); new detections, alerts and camera-health changes appear without refresh; **idempotency keys, temporal dedup and alert cool-down** prevent duplicate / runaway events |
| **12 Scalability** | Edge / regional / central design, sizing, GPU, bandwidth, storage tiers, HA/DR, security, cost: [docs/SCALABILITY.md](docs/SCALABILITY.md) |
| **13 Security** | JWT + RBAC with server-side logout and account lockout, hashed scoped API keys, Fernet-encrypted stream credentials, camera-scoped stream tokens enforced by the gateway, SSRF protection, strict CSP, HTTPS, rate limiting, least-privilege containers bound to localhost, audit log, env-based secrets, 0 known dependency vulnerabilities — see [docs/SECURITY.md](docs/SECURITY.md) |
| **Dashcam (okDriver)** | Vehicle-mounted camera `D001` on a patrol van: GPS heartbeats move its marker live and draw its track, on-device ANPR geotags each read where the van was (so watchlist hits are located on the move), and ADAS / driver-monitoring events (overspeed, harsh braking, collision warning, drowsiness) flow into the same event history |
| **18 Optional extras** | ONVIF mock + discovery, RTSP → HLS/WebRTC gateway with recording & playback, ANPR duplicate suppression, temporal correlation, heartbeat service, role-based views, route reconstruction, low-bandwidth snapshot mode, Docker Compose, tests + CI, Prometheus metrics, Redis event architecture, multi-department registry |

## Quick start

Prerequisites: Docker Desktop (or Docker Engine + Compose v2), `make`, `openssl`. Allow about 4 GB RAM.

```bash
git clone <repo-url> netra && cd netra
make up            # generates .env with random secrets, builds and starts everything
```

Open **https://localhost:8443** and accept the locally-issued certificate (Caddy's internal CA).
Log in with one of the generated accounts; the passwords are printed by `make env` and stored in `.env`:

| User | Role | Can |
|---|---|---|
| `admin` | ADMIN | everything, incl. onboarding, users, API keys, audit |
| `operator` | OPERATOR | acknowledge/resolve alerts, manage watchlist, probe cameras |
| `viewer` | VIEWER | read-only |

To change a password later (hashed with bcrypt and recorded in the audit log):

```bash
docker compose exec backend python -m app.manage set-password admin      # prompts for the new password
```

About 30–60 s after start, all seven demo cameras report ONLINE, the analytics simulator begins
streaming detections and the patrol-van dashcam starts driving its route.

### Demo scenarios

```bash
make scenario-live   # GJ01XX0001 (stolen, CRITICAL) seen at C001 → C002 → C005 → C006, alerts pop up live
make scenario        # same route instantly, using the brief's 10:02 / 10:18 / 10:41 spacing
make clone           # same plate 24 km apart in 2 min → "impossible travel" anomaly on the trace page
make burst           # 10 repeat ANPR reads → 1 stored event with repeat_count = 9
make onboard         # API-based bulk onboarding of cameras C007 and C008
./scripts/camera.sh down c002      # stop a camera stream → C002 turns OFFLINE live (up c002 to restore)
./scripts/camera.sh vendor weak    # vendor NVR reports weak signal → C005 DEGRADED (vendor online)
./scripts/camera.sh edge pause     # edge agent stops heartbeats → C006 DEGRADED then OFFLINE (edge resume)
./scripts/camera.sh dashcam pause  # dashcam loses 4G → D001 DEGRADED then OFFLINE (dashcam resume)
```

### The demo cameras

| ID | Location | Source | How it's integrated | Health |
|---|---|---|---|---|
| C001 | Paldi Cross Roads Junction | RTSP (auth) | Gateway pulls RTSP → LL-HLS | Gateway readiness + inbound bitrate |
| C002 | Subhash Bridge RTO Checkpoint | RTSP (auth) | Gateway pulls RTSP → LL-HLS | same |
| C003 | ISKCON Cross Roads, SG Highway | ONVIF | GetProfiles/GetStreamUri → RTSP → gateway | ONVIF GetDeviceInformation + gateway |
| C004 | Kalupur Railway Station | HLS | Played directly from an existing publisher | Manifest fetch + latency |
| C005 | Vaishnodevi Circle Toll | Vendor REST API | Status + 1 fps snapshot proxy (API key server-side) | Vendor status API |
| C006 | CH-0 Circle, Gandhinagar | RTSP | Gateway → LL-HLS | **Edge-agent heartbeats** |
| D001 | PCR Van 12 (moving) | Dashcam: RTSP over 4G + GPS | Gateway → LL-HLS / WebRTC, recorded | GPS heartbeats (position, speed, heading) |

Every gateway-relayed camera (C001–C003, C006, D001) is recorded in a rolling 6-hour hot tier.
**Live view** can switch to WebRTC (sub-second) from the camera detail or the Live Wall;
**recorded footage** replays from the camera detail, and every alert shows a 40-second
**evidence clip** from around the moment it fired.

The RTSP cameras are FFmpeg-rendered CCTV-style scenes (moving traffic, sensor noise, OSD with a live
clock) published by a separate RTSP server that requires credentials, like real IP cameras. To use
real, legally usable footage, drop `c001.mp4`, `c002.mp4`, `c003.mp4`, `c006.mp4` or `d001.mp4` into [`samples/`](samples/) and run
`docker compose restart camsim`. Any real RTSP / ONVIF camera reachable from Docker can be onboarded
from the UI.

## Architecture

```
 Cameras (RTSP · ONVIF · HLS · Vendor API)          AI engine / edge agent
        │ private camera network                       │ REST (X-API-Key) or Redis Stream
        ▼                                              ▼
 ┌──────────────┐  auth hook  ┌───────────────────────────────────────────────┐
 │ Video gateway│◄───────────►│ FastAPI replicas                               │
 │ MediaMTX     │  path API   │  adapters · ingestion pipeline · watchlist     │
 │ RTSP→LL-HLS  │◄────────────│  matcher · health monitor · REST · WebSocket   │
 └──────┬───────┘             └───────┬─────────────────────┬─────────────────┘
        │ /media                      │ SQL                 │ Pub/Sub · Streams · dedup
        ▼                             ▼                     ▼
 ┌─────────────┐ /api, /ws   ┌──────────────┐        ┌──────────────┐
 │ Caddy HTTPS │◄───────────►│   MySQL 8    │        │    Redis     │
 └──────┬──────┘             └──────────────┘        └──────────────┘
        ▼
 React console (dashboard · map · live wall · alerts · trace · watchlist · audit)
```

Detailed diagrams (system, detection→alert sequence, stream-auth sequence, ER diagram, index
list, security controls) are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Ingestion pipeline:** schema validation → semantic validation (camera enabled, clock skew, event
age) → idempotency on `event_id` → Redis `SET NX` dedup window (repeat reads increment
`repeat_count`) → persist with a location snapshot → watchlist match (exact, or edit-distance-1
fuzzy with severity downgrade) → alert, or update the open alert within the cool-down → commit →
publish to WebSocket clients.

## Project layout

```
backend/            FastAPI service
  app/adapters/     RTSP, ONVIF, HLS, vendor-API source adapters
  app/api/routes/   auth, cameras, events (+search/trace), alerts, watchlist, system (stats, audit, ws)
  app/services/     ingestion, watchlist matcher, dedup, event bus, stream consumer,
                    health monitor, gateway client, rate limiting, audit
  app/models/       SQLAlchemy models
  app/seed.py       idempotent bootstrap (departments, users, cameras, watchlist, history)
  alembic/          migrations
  tests/            pytest suite (38 tests, incl. security and data retention)
frontend/           React + TypeScript console
simulator/          ONVIF mock device, vendor NVR API, AI analytics generator, edge agent,
                    patrol-van dashcam (GPS + ANPR + ADAS), scenarios
infra/              camsim (RTSP cameras), gateway (MediaMTX), caddy, prometheus configs
docs/               architecture, scalability, API, demo script, plan
scripts/            env generation, camera outage simulation
```

## Configuration

All configuration comes from environment variables (`.env`, generated by `make env`; template in
[.env.example](.env.example)). Nothing secret is committed.

| Variable | Purpose |
|---|---|
| `MYSQL_PASSWORD`, `MYSQL_ROOT_PASSWORD`, `REDIS_PASSWORD` | Data-store credentials |
| `JWT_SECRET` | Signs access and stream tokens; also keys the API-key HMAC |
| `CREDENTIALS_KEY` | Fernet key that encrypts camera credentials at rest |
| `ADMIN_PASSWORD`, `OPERATOR_PASSWORD`, `VIEWER_PASSWORD` | Bootstrap accounts |
| `SEED_API_KEY` | API key of the simulator machine client |
| `CAMSIM_PASSWORD`, `ONVIF_PASSWORD`, `VENDOR_API_KEY` | Credentials of the simulated devices |
| `HTTPS_PORT`, `SITE_ADDRESS`, `TLS_MODE` | Edge proxy (use a real domain + ACME email in production) |
| `BIND_ADDRESS` | `127.0.0.1` (default) = only this computer; `0.0.0.0` = reachable from the network |
| `GATEWAY_API_SECRET` | Authenticates the backend to the video gateway's control API |
| `EXTERNAL_MEDIA_ORIGINS` | External HLS origins the browser may load (Content-Security-Policy) |
| `API_DOCS_ENABLED` | Set `false` to hide Swagger/OpenAPI on internet-facing deployments |
| `INGEST_MODE` | Simulator transport: `http`, `stream` or `mixed` |
| `SIM_EVENTS_PER_MIN` | Background traffic rate |
| `PUBLIC_HLS_URL` | Source for the direct-HLS demo camera |

Backend tunables (defaults in `backend/app/core/config.py`): `DEDUP_WINDOW_SECONDS` (60),
`ALERT_COOLDOWN_SECONDS` (300), `MIN_MATCH_CONFIDENCE` (0.60), `FUZZY_MATCH_ENABLED`,
`HEALTH_INTERVAL_SECONDS` (10), `HEARTBEAT_DEGRADED_AFTER_S` / `HEARTBEAT_OFFLINE_AFTER_S`,
`STREAM_TOKEN_SECONDS` (300), `STREAM_ON_DEMAND`, rate limits, `CORS_ORIGINS`.

## Database

MySQL 8 (RDS / Aurora compatible). The schema is managed by Alembic and applied automatically on
backend start (`alembic upgrade head`), followed by the idempotent seed (`python -m app.seed`).
Tables: `departments`, `users`, `api_clients`, `cameras`, `detection_events`, `watchlist_entries`,
`alerts`, `audit_logs`. The ER diagram and index rationale are in
[docs/ARCHITECTURE.md §5](docs/ARCHITECTURE.md#5-data-model-er-diagram).

```bash
docker compose exec backend alembic upgrade head    # migrate
docker compose exec backend python -m app.seed      # (re)seed, idempotent
make reset                                           # wipe all volumes
```

## API

Swagger UI: **https://localhost:8443/api/docs** (click *Authorize* and log in). The contract,
event schema, WebSocket messages and curl examples are in [docs/API.md](docs/API.md).

## Development & tests

```bash
# backend (SQLite + in-process fallbacks, no Docker needed)
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
pytest -q                      # 38 tests: security (lockout, logout, SSRF, tokens), auth/RBAC, onboarding, validation, idempotency, dedup,
                               # watchlist exact/fuzzy, alert cool-down, workflow & bulk actions,
                               # trace, stats, dashcam GPS telemetry / geolocated events
ruff check app tests

# frontend
cd frontend && npm install && npm run dev     # proxies /api to localhost:8000
npm run lint && npm run build
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs lint, tests, the frontend build and
the Docker image builds on every push.

Observability: `docker compose --profile observability up -d prometheus` → http://localhost:9090
(metrics: `netra_events_total`, `netra_alerts_total`, `netra_ingest_seconds`, `netra_cameras`,
`netra_ws_connections`, plus gateway metrics).

## Known limitations

* **AI inference is simulated.** The platform consumes inference results (as the brief allows); a
  real deployment would run a detector + OCR (e.g. YOLOv8 + PaddleOCR on DeepStream) at the edge and
  post to the same API.
* **Demo camera feeds are synthetic** (FFmpeg-rendered scenes and a public HLS test stream). Real
  RTSP / ONVIF cameras work through the same adapters; footage can be dropped into `samples/`.
* **ONVIF discovery** probes configured hosts instead of WS-Discovery multicast, which does not
  cross Docker networks. Production would run discovery on the edge gateway.
* **WebRTC** needs UDP/TCP port 8189 reachable from the browser; if it can't connect within
  8 s the player falls back to LL-HLS automatically.
* **Recording** is a 6-hour rolling hot tier on the gateway volume (demo sizing); warm/cold
  tiers are described in the scalability note, not implemented.
* **Single region.** Department-scoped data access (multi-tenancy) is modelled (departments on
  cameras and users) but not yet enforced per query.
* The local TLS certificate comes from Caddy's internal CA, so browsers warn once. Set
  `SITE_ADDRESS` + `TLS_MODE=<email>` for automatic Let's Encrypt.
* The dashcam drives straight lines between junctions (no road snapping) and its video is
  synthetic.

## What I would do next

1. PTZ control over ONVIF and two-way audio for dashcams.
2. Real edge inference container (YOLOv8n + PaddleOCR) publishing to the Redis Stream / Kafka.
3. Promote alert evidence clips from the gateway's hot tier to object storage with legal hold.
4. Enforce department-level data scoping and SSO (OIDC) with MFA.
5. Kafka + ClickHouse for state-scale event volume, and partitioned MySQL tables.
6. Playwright end-to-end tests of the operator workflow.

## Troubleshooting

* **`docker compose build` hangs while pulling base images on macOS.** Docker Desktop's credential
  helper can block waiting on a Keychain prompt. Unlock or approve the prompt, or build with a
  config that has no `credsStore`: `mkdir -p /tmp/dcfg && echo '{}' > /tmp/dcfg/config.json &&
  DOCKER_CONFIG=/tmp/dcfg docker compose build` (on macOS also set
  `DOCKER_HOST=unix://$HOME/.docker/run/docker.sock`).
* **Port 8443 is busy.** Set `HTTPS_PORT=9443` in `.env`.
* **C004 is OFFLINE.** The public HLS test stream needs internet access; set `PUBLIC_HLS_URL`.
