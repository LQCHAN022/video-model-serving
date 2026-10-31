# Video Model Serving Demo

A minimal example of serving a YOLO model on live video streams (UDP multicast, RTSP, HTTP, files).

```
┌──────────┐  stream URL   ┌──────────────────────┐  JPEG frame  ┌──────────────────────┐
│ Browser  │ ────────────▶ │ gateway   :8090      │ ───────────▶ │ model-server  :8001  │
│ (canvas) │               │ - decodes stream     │              │ - YOLO11s on GPU     │
│          │ ◀──────────── │ - keeps latest frame │ ◀─────────── │ - dynamic batching   │
└──────────┘  WebSocket:   │ - serves frontend    │  detections  │ - POST /predict      │
              dets + JPEG  └──────────────────────┘              └──────────────────────┘
```

| Service | What it does |
|---|---|
| `model-server/` | FastAPI + Ultralytics. `POST /predict` takes a JPEG body and returns `{detections:[{box,conf,label}], infer_ms, batch_size}`. Requests that arrive together, e.g. from several streams, run as one GPU batch (`MAX_BATCH`, `MAX_WAIT_MS`). |
| `gateway/` | Serves the frontend. Each browser stream opens a WebSocket `/ws?url=...`. The gateway decodes the stream with OpenCV/FFmpeg, **keeps only the newest frame** (no backlog when inference is slower than the stream), calls the model server, and sends detections plus that same frame back, so boxes always match the image. |
| `streamer/` | Demo source: loops `streamer/media/sample.mp4` to `udp://239.255.0.1:5000` as MPEG-TS. |

Browsers can't play multicast or RTSP directly, which is why video reaches the browser through the gateway.

## Run with Docker Compose

Requires Docker Desktop with the WSL2 backend and the NVIDIA driver (GPU passthrough is automatic on WSL2).

```bash
docker compose up --build
```

Open http://localhost:8090 and click **Add stream** (the default URL is the demo multicast stream).
To demo several streams, click **Add stream** again, or start more streamers with other addresses:

```bash
docker compose run -d -e MCAST_URL="udp://239.255.0.2:5000?pkt_size=1316&ttl=4" streamer
```

## Run locally for development (venvs)

```bash
# model server (GPU)
cd model-server
python -m venv .venv
.venv/Scripts/activate            # Linux/macOS: source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
pip install -r requirements.txt
uvicorn app:app --port 8001

# gateway (second terminal)
cd gateway
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
uvicorn app:app --port 8090 --reload

# demo multicast source (third terminal, needs ffmpeg on PATH), loops until Ctrl+C
stream.bat                                  # sample.mp4 -> udp://239.255.0.1:5000
stream.bat my.mp4 239.255.0.2:5000          # any video / address
```

## Multicast and Docker networking

- **Inside compose**, the streamer and gateway share a bridge network, so the demo multicast works out of the box.
- **Real multicast from your LAN** does not reach containers under Docker Desktop on Windows, because containers sit behind the WSL2 VM's NAT. Options:
  - Run the **gateway from its venv** on Windows. It joins the multicast group on the host's network, and it can still use the containerised model server through `MODEL_SERVER_URL=http://localhost:8001`.
  - On a Linux host, set `network_mode: host` on the gateway (and point `MODEL_SERVER_URL` at `http://localhost:8001`).
- If Windows Firewall prompts for Python the first time you receive multicast, allow it on private networks.

## Config (env vars)

| Var | Service | Default |
|---|---|---|
| `MODEL_NAME` | model-server | `yolo11s.pt` |
| `DEVICE` | model-server | `0` if CUDA is available, else `cpu` |
| `CONF` | model-server | `0.35` |
| `MAX_BATCH` / `MAX_WAIT_MS` | model-server | `8` / `5` |
| `MODEL_SERVER_URL` | gateway | `http://localhost:8001` |
| `MAX_WIDTH` / `JPEG_QUALITY` | gateway | `960` / `80` |

## Notes and limits

- The displayed frame rate is the inference rate, not the source frame rate. Frames that arrive while inference is busy are dropped.
- File sources (e.g. `http://.../video.mp4`) are read as fast as they decode, so they play sped up. Live sources (multicast, RTSP) play at real time.
- Each browser stream gets its own decoder. Two tabs on the same URL decode it twice.
