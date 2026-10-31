FROM pytorch/pytorch:2.5.1-cuda12.4-cudnn9-runtime

# OpenCV (pulled in by ultralytics) needs these system libs
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the weights into the image so startup needs no download
ARG MODEL_NAME=yolo11s.pt
ENV MODEL_NAME=${MODEL_NAME}
RUN python -c "from ultralytics import YOLO; YOLO('${MODEL_NAME}')"

COPY app.py .
EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
