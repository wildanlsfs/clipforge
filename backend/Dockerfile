FROM python:3.11-slim

# ffmpeg with libass (captions) + libx264 (encode); curl to fetch the
# face-detection model at build time so no network call is needed at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# YuNet face detector (ONNX, ~340KB, Apache-2.0, from opencv/opencv_zoo).
# If this fetch ever fails (network-restricted build), reframer.py falls
# back to OpenCV's bundled Haar cascade automatically -- not fatal.
RUN mkdir -p /app/app/models && \
    curl -fsSL -o /app/app/models/face_detection_yunet.onnx \
        https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx \
    || echo "YuNet download failed, will fall back to Haar cascade at runtime"

COPY app ./app

RUN mkdir -p /data/tmp /data/clips /data/sources
ENV DATA_DIR=/data TMP_DIR=/data/tmp

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
