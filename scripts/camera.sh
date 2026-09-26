#!/bin/sh
# Simulate a camera outage / recovery for demos.
#   scripts/camera.sh down c002   -> stream stops, C002 goes OFFLINE on the dashboard
#                                    (streams: c001 c002 c003 c006 d001)
#   scripts/camera.sh up c002
#   scripts/camera.sh vendor weak|offline|online   -> C005 (vendor API) DEGRADED / OFFLINE / ONLINE
#   scripts/camera.sh edge pause|resume            -> C006 heartbeats stop / resume
#   scripts/camera.sh dashcam pause|resume         -> D001 (patrol-van dashcam) loses 4G / reconnects
set -e
cd "$(dirname "$0")/.."
case "$1" in
  down) docker compose exec camsim curl -s -X DELETE "http://127.0.0.1:9997/v3/config/paths/delete/$2" && echo "$2 down" ;;
  up)
    case "$2" in c001) L="C001 PALDI X-ROADS  ANPR-01"; V=1;; c002) L="C002 SUBHASH BRIDGE RTO  ANPR-02"; V=2;;
                 c003) L="C003 ISKCON X-ROADS  PTZ-01"; V=3;; c006) L="C006 CH-0 CIRCLE GNR  ANPR-06"; V=4;;
                 d001) L="D001 OKDRIVER DASHCAM  GJ01GP0012"; V=dashcam;; *) echo "unknown stream $2"; exit 1;; esac
    docker compose exec camsim curl -s -X POST "http://127.0.0.1:9997/v3/config/paths/add/$2" \
      -H 'Content-Type: application/json' \
      -d "{\"runOnInit\":\"/publish.sh $2 \\\"$L\\\" $V\",\"runOnInitRestart\":true}" && echo "$2 up" ;;
  vendor) docker compose exec simulator python -m sim.scenario vendor "$2" ;;
  edge)
    if [ "$2" = "pause" ]; then docker compose exec simulator touch /tmp/edge-agent-paused; else docker compose exec simulator rm -f /tmp/edge-agent-paused; fi
    echo "edge agent $2" ;;
  dashcam)
    if [ "$2" = "pause" ]; then docker compose exec simulator touch /tmp/dashcam-paused; else docker compose exec simulator rm -f /tmp/dashcam-paused; fi
    echo "dashcam $2" ;;
  *) sed -n '2,8p' "$0"; exit 1 ;;
esac
