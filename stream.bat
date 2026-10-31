@echo off
rem Loop a video file out as an MPEG-TS stream over UDP multicast (needs ffmpeg on PATH).
rem Usage: stream.bat [video] [multicast_addr:port]
rem   e.g. stream.bat                                   (sample video -> 239.255.0.1:5000)
rem        stream.bat my.mp4 239.255.0.2:5000

set "VIDEO=%~1"
if "%VIDEO%"=="" set "VIDEO=%~dp0streamer\media\sample.mp4"
set "ADDR=%~2"
if "%ADDR%"=="" set "ADDR=239.255.0.1:5000"

echo Streaming "%VIDEO%" to udp://%ADDR%  (Ctrl+C to stop)
ffmpeg -hide_banner -loglevel warning -re -stream_loop -1 -i "%VIDEO%" ^
  -an -c:v libx264 -preset veryfast -tune zerolatency -g 24 ^
  -f mpegts "udp://%ADDR%?pkt_size=1316&ttl=4"
