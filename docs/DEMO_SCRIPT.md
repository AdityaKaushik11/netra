# Demo video script (target: 4–5 minutes)

**Before recording**
* `make up`, wait ~1 min, open `https://localhost:8443` (accept the local certificate once).
* Log in as `admin` (password in `.env`). Keep a terminal visible beside the browser.
* Turn the sound on (alert tone). Close other tabs.
* Optional: start from a clean slate with `make reset && make up` (wait 1–2 min so recordings exist
  for the evidence clips).

| Time | Screen | Say / do |
|---|---|---|
| 0:00–0:20 | Dashboard | "Netra is a working CCTV monitoring and analytics platform: FastAPI, MySQL, Redis, a MediaMTX video gateway and a React console, all in Docker Compose." Point at the KPI strip, map, active alerts, live grid, streaming detections. |
| 0:20–0:50 | Live Wall | "Five logically different sources in one view: RTSP IP cameras relayed by the gateway, an ONVIF camera whose stream URI is discovered over SOAP, an existing HLS publisher, a vendor NVR that only offers a REST snapshot API, and a moving okDriver-style dashcam on a patrol van." Tick **WebRTC low latency** to show sub-second video. |
| 0:50–1:10 | Dashboard map → D001 | Click the purple arrow: the dashcam's GPS track, live speed/heading, and its detections, including ADAS events (overspeed, harsh braking), geotagged where the van was. |
| 1:10–1:40 | Cameras | Filter by protocol/status. Open C001: live feed, metadata, encrypted credentials, health metrics, audit history. Click **ONVIF discovery** → Scan (password = `ONVIF_PASSWORD`) → onboard as C009 → marker appears. Then in the terminal `make onboard` (API-based bulk onboarding) → C007/C008 appear live without refresh. |
| 1:40–2:10 | Terminal + Dashboard | `./scripts/camera.sh down c002` → within ~20 s C002 turns red, toast "went OFFLINE". `./scripts/camera.sh vendor weak` → C005 DEGRADED. Restore with `up c002` / `vendor online`. |
| 2:10–3:00 | Terminal + Dashboard | `make scenario-live` → GJ01XX0001 (stolen, CRITICAL) is read at C001, C002, C005, C006. Each read raises/updates an alert instantly: toast with plate, camera, time, confidence, beep, map marker pulses. |
| 3:00–3:30 | Alerts | Open the C001 alert: **live feed and a recorded evidence clip of the moment it fired**, map, case reference. Acknowledge with a note, then resolve. Mention alert cool-down (`hit_count`) and bulk handling instead of alert storms. |
| 3:30–4:00 | Trace | Search GJ01XX0001: chronological timeline 10:02 → 10:18 → 10:41 style, distances, implied speeds, numbered route on the map. `make clone` → trace GJ01XX2468 shows the "impossible travel / cloned plate" anomaly. |
| 4:00–4:30 | Swagger (`/api/docs`) | Show `POST /events`: the pipeline (validate → idempotency → dedup → store → watchlist → alert → WebSocket). Run `make burst` in the terminal: 10 reads → 1 event with repeat_count 9. |
| 4:30–5:00 | `docs/ARCHITECTURE.md` diagram, `docs/SCALABILITY.md` | "Edge analytics + metadata-only uplink, regional gateways with on-demand pulls, stateless API replicas with Redis/Kafka fan-out, partitioned MySQL, hot/warm/cold storage — the path to 80,000 cameras." Close on the audit log page. |
