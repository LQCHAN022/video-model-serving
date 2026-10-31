"""End-to-end check: open N streams through the gateway and confirm frames + detections arrive.

Usage (gateway venv has the deps):  python scripts/smoke_test.py [stream_url] [num_streams]
"""
import asyncio
import json
import sys
from urllib.parse import quote

import websockets

GATEWAY = "ws://localhost:8090/ws?url="
URL = sys.argv[1] if len(sys.argv) > 1 else "udp://239.255.0.1:5000"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
FRAMES = 30


async def watch(i: int) -> dict:
    async with websockets.connect(GATEWAY + quote(URL, safe=""), max_size=None) as ws:
        frames, objects, batches, meta = 0, 0, [], None
        while frames < FRAMES:
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
            if isinstance(msg, str):
                meta = json.loads(msg)
                if "status" in meta:
                    print(f"[{i}] status: {meta['status']}")
                    meta = None
            else:
                assert meta is not None and msg[:2] == b"\xff\xd8", "frame must follow its detections and be a JPEG"
                frames += 1
                objects += len(meta["detections"])
                batches.append(meta["batch_size"])
        return {"stream": i, "frames": frames, "avg_objects": objects / frames,
                "max_batch": max(batches), "last_infer_ms": meta["infer_ms"], "last_roundtrip_ms": meta["roundtrip_ms"]}


async def main():
    results = await asyncio.gather(*(watch(i) for i in range(N)))
    for r in results:
        print(r)
    # Some stretches of a video legitimately contain no objects, so only require detections overall
    assert any(r["avg_objects"] > 0 for r in results), "expected some detections"
    print("PASS")


asyncio.run(main())
