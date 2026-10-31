"""YOLO model server.

POST /predict with a JPEG body, get back boxes/labels as JSON.
Concurrent requests (e.g. from several streams) are grouped by a small
dynamic batcher so the GPU runs one forward pass per batch.
"""
import asyncio
import os
import time
from contextlib import asynccontextmanager

import cv2
import numpy as np
import torch
from fastapi import FastAPI, HTTPException, Request
from ultralytics import YOLO

MODEL_NAME = os.getenv("MODEL_NAME", "yolo11s.pt")
DEVICE = os.getenv("DEVICE", "0" if torch.cuda.is_available() else "cpu")
CONF = float(os.getenv("CONF", "0.35"))
MAX_BATCH = int(os.getenv("MAX_BATCH", "8"))
MAX_WAIT_MS = float(os.getenv("MAX_WAIT_MS", "5"))

model = YOLO(MODEL_NAME)
queue: asyncio.Queue  # items: (image, future)


def to_json(result) -> list[dict]:
    boxes = result.boxes
    return [
        {
            "box": [round(v, 1) for v in xyxy],  # x1, y1, x2, y2 in pixels
            "conf": round(conf, 3),
            "label": result.names[int(cls)],
        }
        for xyxy, conf, cls in zip(boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist())
    ]


async def batch_worker():
    loop = asyncio.get_running_loop()
    while True:
        batch = [await queue.get()]
        # Wait briefly for more requests to arrive so they can share a forward pass.
        deadline = loop.time() + MAX_WAIT_MS / 1000
        while len(batch) < MAX_BATCH and (timeout := deadline - loop.time()) > 0:
            try:
                batch.append(await asyncio.wait_for(queue.get(), timeout))
            except asyncio.TimeoutError:
                break

        images = [img for img, _ in batch]
        t0 = time.perf_counter()
        try:
            results = await asyncio.to_thread(model.predict, images, device=DEVICE, conf=CONF, verbose=False)
        except Exception as e:
            for _, fut in batch:
                fut.set_exception(e)
            continue
        infer_ms = (time.perf_counter() - t0) * 1000
        for (_, fut), result in zip(batch, results):
            fut.set_result({"detections": to_json(result), "infer_ms": round(infer_ms, 1), "batch_size": len(batch)})


@asynccontextmanager
async def lifespan(app: FastAPI):
    global queue
    queue = asyncio.Queue()
    model.predict(np.zeros((640, 640, 3), dtype=np.uint8), device=DEVICE, verbose=False)  # warm up
    worker = asyncio.create_task(batch_worker())
    yield
    worker.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
def health():
    return {"model": MODEL_NAME, "device": DEVICE, "max_batch": MAX_BATCH}


@app.post("/predict")
async def predict(request: Request):
    img = cv2.imdecode(np.frombuffer(await request.body(), np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "body must be an encoded image (e.g. JPEG)")
    fut = asyncio.get_running_loop().create_future()
    await queue.put((img, fut))
    return await fut
