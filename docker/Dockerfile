# ===========================================================================
# Vantag Cloud Dockerfile (x86_64)
# ===========================================================================
# Base image: standard Python slim image for cloud/VPS deployment.
# Use this Dockerfile for docker-compose.prod.yml / docker-compose.yml on
# regular x86_64 VPS servers (India, Singapore, Malaysia, Philippines).
#
# NOTE: docker/Dockerfile.edge is a SEPARATE Dockerfile intended only for
# NVIDIA Jetson (ARM64) edge hardware — do not use it for cloud VPS builds.
# ===========================================================================
FROM python:3.11-slim

LABEL maintainer="Vantag Platform <platform@vantag.ai>" \
      description="Vantag retail AI platform — cloud VPS container" \
      version="1.0.0"

WORKDIR /app

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        # OpenCV runtime libraries (headless Python build links to these)
        libgl1 \
        libglib2.0-0 \
        # MQTT broker (co-located, matches edge deployment topology)
        mosquitto \
        mosquitto-clients \
        # Video / codec utilities
        ffmpeg \
        # Build tools for Python packages with C extensions
        gcc \
        g++ \
        cmake \
        # curl / wget for health checks and model downloads
        curl \
        wget \
        # Timezone data (required by some Python packages)
        tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# ---------------------------------------------------------------------------
# Python dependencies
# ---------------------------------------------------------------------------
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

RUN pip install --no-cache-dir torch torchvision \
        --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---------------------------------------------------------------------------
# Application source
# ---------------------------------------------------------------------------
COPY backend/       ./backend/
COPY models/        ./models/
COPY windows_agent/ ./windows_agent/

# Mosquitto configuration (TCP + WebSocket listeners).
COPY docker/mosquitto.conf /etc/mosquitto/mosquitto.conf

# Create runtime directories.
RUN mkdir -p /app/snapshots/reports \
             /app/snapshots/frames \
             /var/log/vantag \
             /var/lib/mosquitto

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV VANTAG_ENV=production
# Disable ultralytics telemetry.
ENV YOLO_TELEMETRY=False
# Timezone.
ENV TZ=UTC

# ---------------------------------------------------------------------------
# Ports
# 8800  — FastAPI REST + WebSocket (matches docker-compose.prod.yml)
# 1883  — MQTT TCP
# 9001  — MQTT over WebSocket
# ---------------------------------------------------------------------------
EXPOSE 8800 1883 9001

# ---------------------------------------------------------------------------
# Health check — polls the FastAPI /health endpoint every 30 s.
# ---------------------------------------------------------------------------
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8800/health || exit 1

# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
# Start Mosquitto in the background, then launch Uvicorn.
CMD ["sh", "-c", \
     "mosquitto -c /etc/mosquitto/mosquitto.conf -d && \
      uvicorn backend.api.main:app \
          --host 0.0.0.0 \
          --port 8800 \
          --workers 2 \
          --proxy-headers \
          --forwarded-allow-ips '*' \
          --log-level info"]
