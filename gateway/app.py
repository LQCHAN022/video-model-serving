"""Stream gateway.

The browser opens a WebSocket at /ws?url=<stream url>. For each connection the
gateway decodes the stream, sends the newest frame to the model server, and
pushes the frame plus its detections back to the browser, so boxes and video
are always in sync.
"""
import asyncio
import json
import logging
import os
import threading
import time
from pathlib import Path

# Must be set before OpenCV opens a stream: larger UDP buffer, and don't abort on overruns
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "fifo_size;5000000|overrun_nonfatal;1")

import cv2
import httpx
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

MODEL_SERVER_URL = os.getenv("MODEL_SERVER_URL", "http://localhost:8001")
MAX_WIDTH = int(os.getenv("MAX_WIDTH", "960"))
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "80"))

log = logging.getLogger("uvicorn.error")
app = FastAPI()
http = httpx.AsyncClient(base_url=MODEL_SERVER_URL, timeout=10)


class LatestFrameReader:
    """Decodes a stream in a background thread, keeping only the newest frame.

    Older frames are dropped: if inference is slower than the stream, we skip
    ahead instead of building up a backlog (and ever-growing latency).
    """

    def __init__(self, url: str):
        self.url = url
        self.status = "connecting"
        self._frame = None
        self._seq = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self._stop.is_set():
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            if cap.isOpened():
                self.status = "playing"
                while not self._stop.is_set():
                    ok, frame = cap.read()
                    if not ok:
                        break
                    with self._lock:
                        self._frame, self._seq = frame, self._seq + 1
            cap.release()
            if not self._stop.is_set():
                self.status = "reconnecting"  # source dropped or not up yet; keep retrying
                self._stop.wait(1)

    def latest(self):
        with self._lock:
            return self._frame, self._seq

    def stop(self):
        self._stop.set()


@app.websocket("/ws")
async def stream(websocket: WebSocket, url: str):
    await websocket.accept()
    reader = LatestFrameReader(url)
    last_seq, last_status = 0, None
    try:
        while True:
            frame, seq = reader.latest()
            if seq == last_seq:
                if reader.status != last_status:
                    last_status = reader.status
                    await websocket.send_text(json.dumps({"status": reader.status}))
                await asyncio.sleep(0.005)
                continue
            last_seq = seq

            h, w = frame.shape[:2]
            if w > MAX_WIDTH:
                frame = cv2.resize(frame, (MAX_WIDTH, round(h * MAX_WIDTH / w)))
            jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])[1].tobytes()

            t0 = time.perf_counter()
            try:
                resp = await http.post("/predict", content=jpeg, headers={"content-type": "image/jpeg"})
                resp.raise_for_status()
            except httpx.HTTPError as e:
                await websocket.send_text(json.dumps({"status": f"model server error: {e!r}"}))
                await asyncio.sleep(1)
                continue
            result = resp.json() | {"roundtrip_ms": round((time.perf_counter() - t0) * 1000, 1)}

            # Metadata first, then the exact frame it belongs to
            await websocket.send_text(json.dumps(result))
            await websocket.send_bytes(jpeg)
    except Exception as e:  # client disconnects surface here as various exception types
        log.info("stream %s closed: %r", url, e)
    finally:
        reader.stop()


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
