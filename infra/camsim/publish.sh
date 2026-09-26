#!/bin/sh
# publish.sh <path> <osd label> <variant>
# Renders a CCTV-like junction scene (road, lane markings, moving vehicles, sensor noise, OSD
# with live clock) and publishes it over RTSP. Uses /samples/<path>.mp4 instead when present.
P="$1"; LABEL="$2"; V="${3:-1}"
FONT=/usr/share/fonts/dejavu/DejaVuSansMono.ttf
OSD="drawtext=fontfile=$FONT:text='$LABEL':x=14:y=12:fontsize=20:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=6,\
drawtext=fontfile=$FONT:text='%{localtime}':x=w-tw-14:y=12:fontsize=20:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=6,\
drawtext=fontfile=$FONT:text='REC':x=w-60:y=h-34:fontsize=18:fontcolor=red"
OUT="-c:v libx264 -preset ultrafast -tune zerolatency -profile:v baseline -pix_fmt yuv420p -g 24 -b:v 700k -maxrate 900k -bufsize 900k -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/$P"

if [ -f "/samples/$P.mp4" ]; then
  exec ffmpeg -hide_banner -loglevel error -re -stream_loop -1 -i "/samples/$P.mp4" -an \
    -vf "scale=960:540,$OSD" $OUT
fi

if [ "$V" = "dashcam" ]; then
  # Forward-facing dashcam view: road ahead, lane dashes rushing towards the camera,
  # vehicles ahead, dashboard at the bottom, 4G/GPS OSD.
  exec ffmpeg -hide_banner -loglevel error -re \
    -f lavfi -i "color=c=0x6f8fae:s=960x540:r=15" \
    -f lavfi -i "color=c=0xe8e070:s=10x46:r=15" \
    -f lavfi -i "color=c=0xa82424:s=110x70:r=15" \
    -f lavfi -i "color=c=0xd8d8d8:s=90x60:r=15" \
    -filter_complex "\
[0]drawbox=x=0:y=250:w=960:h=290:c=0x4a4d52:t=fill,drawbox=x=0:y=250:w=960:h=6:c=0x2f5d34:t=fill,\
drawbox=x=0:y=470:w=960:h=70:c=0x151515:t=fill[bg];\
[bg][1]overlay=x=475:y='250+mod(t*260\,220)':eval=frame[a];\
[a][1]overlay=x=475:y='250+mod(t*260+110\,220)':eval=frame[b];\
[b][2]overlay=x='300+40*sin(t/3)':y='300+20*sin(t/2)':eval=frame[c];\
[c][3]overlay=x='560+30*sin(t/4)':y='280+10*sin(t/5)':eval=frame[d];\
[d]noise=alls=10:allf=t,$OSD,drawtext=fontfile=$FONT:text='GPS FIX  4G LTE':x=14:y=h-34:fontsize=18:fontcolor=0x9fe89f[out]" \
    -map "[out]" $OUT
fi

case "$V" in
  1) BG=0x3b4046; S1=140; S2=190; S3=260 ;;
  2) BG=0x444a44; S1=110; S2=170; S3=230 ;;
  3) BG=0x3a3d4a; S1=160; S2=120; S3=210 ;;
  *) BG=0x40403c; S1=130; S2=200; S3=250 ;;
esac
exec ffmpeg -hide_banner -loglevel error -re \
  -f lavfi -i "color=c=$BG:s=960x540:r=12" \
  -f lavfi -i "color=c=0xd8d8d8:s=96x46:r=12" \
  -f lavfi -i "color=c=0xa82424:s=120x54:r=12" \
  -f lavfi -i "color=c=0x23449c:s=64x34:r=12" \
  -f lavfi -i "color=c=0x151515:s=150x62:r=12" \
  -filter_complex "\
[0]drawbox=x=0:y=140:w=960:h=5:c=white@0.8:t=fill,drawbox=x=0:y=400:w=960:h=5:c=white@0.8:t=fill,\
drawbox=x=0:y=268:w=960:h=4:c=yellow@0.7:t=fill,drawbox=x=0:y=145:w=960:h=255:c=0x55595e@0.35:t=fill[bg];\
[bg][1]overlay=x='mod(t*$S1\,1100)-100':y=180:eval=frame[a];\
[a][2]overlay=x='960-mod(t*$S2+300\,1250)':y=300:eval=frame[b];\
[b][3]overlay=x='mod(t*$S3+500\,1150)-120':y=210:eval=frame[c];\
[c][4]overlay=x='960-mod(t*($S1-40)+700\,1400)':y=325:eval=frame[d];\
[d]noise=alls=12:allf=t,$OSD[out]" \
  -map "[out]" $OUT
