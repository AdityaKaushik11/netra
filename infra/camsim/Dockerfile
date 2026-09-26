# Simulated IP cameras: an RTSP server (MediaMTX) fed by FFmpeg-rendered CCTV-style scenes.
# Drop legally usable footage into ./samples/<cam>.mp4 to replace a synthetic scene.
FROM bluenviron/mediamtx:1-ffmpeg
RUN apk add --no-cache font-dejavu tzdata curl
COPY entrypoint.sh publish.sh /
RUN chmod +x /entrypoint.sh /publish.sh
ENTRYPOINT ["/entrypoint.sh"]
