# Demo source: loops a video file out as an MPEG-TS stream over UDP multicast
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV VIDEO=/media/sample.mp4 \
    MCAST_URL="udp://239.255.0.1:5000?pkt_size=1316&ttl=4"
CMD ffmpeg -hide_banner -loglevel warning -re -stream_loop -1 -i "$VIDEO" \
    -an -c:v libx264 -preset veryfast -tune zerolatency -g 24 -f mpegts "$MCAST_URL"
