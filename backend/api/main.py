"""
backend/api/main.py
====================
FastAPI application entry point for the Vantag retail security platform.

Startup sequence (lifespan)
---------------------------
1. Instantiate ``VantagPipeline`` (loads camera registry).
2. Connect ``MQTTClient`` to the broker.
3. Start ``StreamManager`` (RTSP threads) and ``HealthMonitor``.
4. Start pipeline processing tasks.
5. Inject pipeline reference into all API routers.

Shutdown sequence (lifespan)
-----------------------------
1. Stop pipeline and all camera tasks.
2. Stop MQTT client.
3. Stop StreamManager and HealthMonitor.

Running
-------
    uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .models import HealthResponse
from .pipeline import VantagPipeline
from .websocket_router import manager as ws_manager
from .websocket_router import router as ws_router
from .stores_router import router as stores_router
from .stores_router import queue_router
from .stores_router import set_pipeline as stores_set_pipeline
from .cameras_router import router as cameras_router
from .cameras_router import set_pipeline as cameras_set_pipeline
from .reports_router import router as reports_router
from .reports_router import set_pipeline as reports_set_pipeline
from .watchlist_router import router as watchlist_router
from ..audio.intercom import router as audio_router
from ..mqtt.client import MQTTClient
from ..mqtt.door_controller import DoorController, door_router, set_controller
from ..pos.pos_router import router as pos_router
from ..webhooks.webhook_engine import WebhookEngine
from ..db.database import init_db
from .auth_router import auth_router
from .onboarding_router import onboarding_router
from .tenants_router import tenants_router
from .edge_router import edge_router
from .billing_router import billing_router
from .camera_probe_router import camera_probe_router
from .demo_router import router as demo_router
from .demo_router import set_pipeline as demo_set_pipeline
from .zone_router import router as zone_router

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_SNAPSHOTS_DIR = _BASE_DIR / "snapshots"
_CONFIG_PATH = _BASE_DIR / "backend" / "config" / "cameras.yaml"

# ---------------------------------------------------------------------------
# CORS configuration
# Allow all origins in development; restrict in production via env var.
# Set VANTAG_ALLOWED_ORIGINS="https://app.example.com,https://admin.example.com"
# ---------------------------------------------------------------------------

_raw_origins = os.getenv("VANTAG_ALLOWED_ORIGINS", "*")
_ALLOWED_ORIGINS = (
    ["*"] if _raw_origins == "*" else [o.strip() for o in _raw_origins.split(",")]
)

# ---------------------------------------------------------------------------
# Application-level singletons (populated during lifespan)
# ---------------------------------------------------------------------------

_pipeline: VantagPipeline | None = None
_mqtt_client: MQTTClient | None = None
_door_controller: DoorController | None = None
_app_start_time: float = time.monotonic()


# ---------------------------------------------------------------------------
# Lifespan context manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application-wide resource lifecycle."""
    global _pipeline, _mqtt_client, _door_controller, _app_start_time  # noqa: PLW0603

    logger.info("Vantag API starting up...")

    # ------------------------------------------------------------------
    # 1. Instantiate pipeline (loads camera registry synchronously).
    # ------------------------------------------------------------------
    try:
        config_path = str(_CONFIG_PATH) if _CONFIG_PATH.exists() else None
        _pipeline = VantagPipeline(
            config_path=config_path,
            ws_broadcast=ws_manager.broadcast,
        )
        _mqtt_client = _pipeline._mqtt  # noqa: SLF001
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create VantagPipeline | error=%s", exc)
        raise

    # ------------------------------------------------------------------
    # 2. MQTT door controller.
    # ------------------------------------------------------------------
    _door_controller = DoorController(_mqtt_client)
    set_controller(_door_controller)

    # ------------------------------------------------------------------
    # 3. Inject pipeline into routers.
    # ------------------------------------------------------------------
    stores_set_pipeline(_pipeline)
    cameras_set_pipeline(_pipeline)
    reports_set_pipeline(_pipeline)
    demo_set_pipeline(_pipeline)

    # ------------------------------------------------------------------
    # 3b. Initialise webhook engine and POS integration.
    # ------------------------------------------------------------------
    from ..pos.pos_router import set_webhook_engine
    _webhook_engine = WebhookEngine(
        config_path=str(Path(__file__).parent.parent / "webhooks" / "webhooks.yaml")
    )
    set_webhook_engine(_webhook_engine)

    # ------------------------------------------------------------------
    # 4. Snapshot directories + SQLite incident store.
    # ------------------------------------------------------------------
    _SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    (_SNAPSHOTS_DIR / "watchlist").mkdir(exist_ok=True)
    (_SNAPSHOTS_DIR / "reports").mkdir(exist_ok=True)

    # Initialise local SQLite audit store and purge events older than 30 days.
    try:
        from ..db import incident_store as _istore
        _istore.init_db()
        deleted = _istore.cleanup_old(30)
        if deleted:
            logger.info("Purged %d incident(s) older than 30 days from SQLite", deleted)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SQLite incident store init failed (non-fatal) | error=%s", exc)

    # ------------------------------------------------------------------
    # 5. Start pipeline (RTSP threads + async tasks).
    # ------------------------------------------------------------------
    _app_start_time = time.monotonic()
    await _pipeline.start()
    logger.info("Vantag API ready.")

    # Initialize SaaS database tables
    try:
        await init_db()
        logger.info("SaaS database tables initialized.")
    except Exception as exc:
        logger.warning("DB init skipped (may already exist): %s", exc)

    # ------------------------------------------------------------------
    # Yield control to FastAPI.
    # ------------------------------------------------------------------
    yield

    # ------------------------------------------------------------------
    # Shutdown.
    # ------------------------------------------------------------------
    logger.info("Vantag API shutting down...")
    if _pipeline:
        await _pipeline.stop()
    logger.info("Vantag API shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------


app = FastAPI(
    title="Vantag API",
    version="2.0.0",
    description=(
        "Real-time retail security intelligence platform. "
        "Provides behavioral event streaming, risk scoring, "
        "camera management, watchlist control, and intercom signaling."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Static files (snapshots served at /snapshots/*)
# ---------------------------------------------------------------------------

_SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/snapshots",
    StaticFiles(directory=str(_SNAPSHOTS_DIR)),
    name="snapshots",
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(ws_router)
app.include_router(stores_router)
app.include_router(queue_router)
app.include_router(cameras_router)
app.include_router(reports_router)
app.include_router(watchlist_router)
app.include_router(audio_router)
app.include_router(door_router)
app.include_router(pos_router)
app.include_router(auth_router)
app.include_router(onboarding_router)
app.include_router(tenants_router)
app.include_router(edge_router)
app.include_router(billing_router)
app.include_router(camera_probe_router)
app.include_router(demo_router)
app.include_router(zone_router)

# ---------------------------------------------------------------------------
# Health check endpoint
# ---------------------------------------------------------------------------


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Health"],
    summary="Health check",
)
async def health_check() -> HealthResponse:
    """
    Returns API status, version, and uptime.

    Used by load balancers and monitoring systems to verify the service
    is alive and the pipeline has initialised successfully.
    """
    uptime = time.monotonic() - _app_start_time
    return HealthResponse(
        status="ok",
        version=app.version,
        uptime_seconds=round(uptime, 2),
    )
