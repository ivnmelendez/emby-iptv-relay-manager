#!/bin/sh
set -e
mkdir -p /output

exec ffmpeg -y \
  -re \
  -f lavfi -i "color=c=0x0d0d0d:size=1280x720:rate=25" \
  -f lavfi -i "aevalsrc=0" \
  -c:v libx264 \
  -preset ultrafast \
  -tune zerolatency \
  -b:v 300k \
  -maxrate 300k \
  -bufsize 600k \
  -g 50 \
  -sc_threshold 0 \
  -c:a aac \
  -b:a 32k \
  -f hls \
  -hls_time 4 \
  -hls_list_size 6 \
  -hls_flags delete_segments+append_list \
  /output/offline.m3u8
