#!/bin/sh
# Generates the camera-side RTSP server config. Readers must authenticate like real IP cameras.
set -e
: "${CAMSIM_USER:=viewer}"
: "${CAMSIM_PASSWORD:?CAMSIM_PASSWORD must be set}"
: "${ONVIF_USER:=admin}"
: "${ONVIF_PASSWORD:?ONVIF_PASSWORD must be set}"
cat > /mediamtx.yml <<YAML
logLevel: warn
api: yes
apiAddress: 127.0.0.1:9997
rtspAddress: :8554
rtmp: no
hls: no
webrtc: no
srt: no
authInternalUsers:
  - user: any
    ips: ['127.0.0.1', '::1']
    permissions: [{action: publish}, {action: read}, {action: api}]
  - user: ${CAMSIM_USER}
    pass: ${CAMSIM_PASSWORD}
    permissions: [{action: read}]
  # ONVIF devices usually reuse the device account for RTSP (used by C003)
  - user: ${ONVIF_USER}
    pass: ${ONVIF_PASSWORD}
    permissions: [{action: read}]
paths:
  c001:
    runOnInit: /publish.sh c001 "C001 PALDI X-ROADS  ANPR-01" 1
    runOnInitRestart: yes
  c002:
    runOnInit: /publish.sh c002 "C002 SUBHASH BRIDGE RTO  ANPR-02" 2
    runOnInitRestart: yes
  c003:
    runOnInit: /publish.sh c003 "C003 ISKCON X-ROADS  PTZ-01" 3
    runOnInitRestart: yes
  c006:
    runOnInit: /publish.sh c006 "C006 CH-0 CIRCLE GNR  ANPR-06" 4
    runOnInitRestart: yes
  d001:
    runOnInit: /publish.sh d001 "D001 OKDRIVER DASHCAM  GJ01GP0012" dashcam
    runOnInitRestart: yes
YAML
exec /mediamtx /mediamtx.yml
