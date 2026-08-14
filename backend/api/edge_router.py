"""
backend/api/edge_router.py
==========================
Edge Agent API — registration, heartbeat, event ingestion.
Called by the Android app and Windows Edge Agent.

Routes
------
POST /api/edge/register              – authenticated registration (X-API-Key)
POST /api/edge/register/bootstrap    – one-time bootstrap (registration_token required)
POST /api/edge/heartbeat             – authenticated heartbeat (X-API-Key)
POST /api/edge/events                – ingest detection event (X-API-Key)
GET  /api/edge/config                – poll latest camera config (X-API-Key)
GET  /api/edge/agents                – list tenant's agents + live status (JWT)
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_session
from ..db.models.tenant import EdgeAgent, Tenant
from ..db.models.camera import CameraConfig
from ..db.models.event import DetectionEvent
from ..db.models.site import derive_legacy_store_id
from ..middleware.tenant_middleware import get_current_user_id
from ..services.tenant_alerts import dispatch_tenant_alert
from ..services import staff_face_service
from ..services import vlm_verification_service
from .watchlist_router import record_match

edge_router = APIRouter(prefix="/api/edge", tags=["edge-agent"])

logger = logging.getLogger("vantag.edge")


def _normalized_people_count_zones(c) -> list[dict]:
    """Return the camera's people-count zones with bbox normalized to 0-1.

    Zones are stored in reference-resolution pixels (the camera's configured
    resolution, default 1920x1080). The edge agent processes downscaled
    frames, so absolute pixel bboxes never match. Sending normalized
    fractions lets the agent scale to whatever frame size it decodes.
    """
    zones = (
        (getattr(c, "analyzer_config", None) or {})
        .get("people_count", {})
        .get("zones", [])
    )
    ref_w = float(getattr(c, "resolution_width", None) or 1920)
    ref_h = float(getattr(c, "resolution_height", None) or 1080)
    out: list[dict] = []
    for z in zones:
        bbox = z.get("bbox") or []
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = (float(v) for v in bbox)
        # Already normalized (legacy safety): all values within [0, 1].
        if max(x1, y1, x2, y2) <= 1.0:
            norm = [x1, y1, x2, y2]
        else:
            norm = [
                max(0.0, min(1.0, x1 / ref_w)),
                max(0.0, min(1.0, y1 / ref_h)),
                max(0.0, min(1.0, x2 / ref_w)),
                max(0.0, min(1.0, y2 / ref_h)),
            ]
        out.append({**z, "bbox": norm, "normalized": True})
    return out


def _normalized_exclusion_zones(c) -> list[dict]:
    """Return the camera's ROI-exclusion zones with bbox normalized to 0-1.

    Same reference-resolution → fraction conversion as
    ``_normalized_people_count_zones`` above, applied to zones stored under
    ``analyzer_config.exclusion.zones``.
    """
    zones = (
        (getattr(c, "analyzer_config", None) or {})
        .get("exclusion", {})
        .get("zones", [])
    )
    ref_w = float(getattr(c, "resolution_width", None) or 1920)
    ref_h = float(getattr(c, "resolution_height", None) or 1080)
    out: list[dict] = []
    for z in zones:
        bbox = z.get("bbox") or []
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = (float(v) for v in bbox)
        if max(x1, y1, x2, y2) <= 1.0:
            norm = [x1, y1, x2, y2]
        else:
            norm = [
                max(0.0, min(1.0, x1 / ref_w)),
                max(0.0, min(1.0, y1 / ref_h)),
                max(0.0, min(1.0, x2 / ref_w)),
                max(0.0, min(1.0, y2 / ref_h)),
            ]
        out.append({**z, "bbox": norm, "normalized": True})
    return out

def _normalized_inventory_zones(c) -> list[dict]:
    """Return the camera's shelf/inventory zones with bbox normalized to 0-1.

    Same reference-resolution → fraction conversion as
    ``_normalized_people_count_zones`` above, applied to zones stored under
    ``analyzer_config.inventory_movement.zones`` (the Zone Editor's Shelf/
    Inventory zone type). These zones were previously saved to the DB by the
    Zone Editor UI but never sent to the edge agent at all, so a configured
    shelf zone had zero effect on real detection — this is the fix.
    """
    zones = (
        (getattr(c, "analyzer_config", None) or {})
        .get("inventory_movement", {})
        .get("zones", [])
    )
    ref_w = float(getattr(c, "resolution_width", None) or 1920)
    ref_h = float(getattr(c, "resolution_height", None) or 1080)
    out: list[dict] = []
    for z in zones:
        bbox = z.get("bbox") or []
        if len(bbox) != 4:
            continue
        x1, y1, x2, y2 = (float(v) for v in bbox)
        if max(x1, y1, x2, y2) <= 1.0:
            norm = [x1, y1, x2, y2]
        else:
            norm = [
                max(0.0, min(1.0, x1 / ref_w)),
                max(0.0, min(1.0, y1 / ref_h)),
                max(0.0, min(1.0, x2 / ref_w)),
                max(0.0, min(1.0, y2 / ref_h)),
            ]
        out.append({**z, "bbox": norm, "normalized": True})
    return out


def _normalized_high_value_counter(c) -> dict:
    """Return the camera's High-Value Counter (jewellery / luxury) polygons
    with each polygon's vertices normalized to 0-1 fractions of the camera's
    reference resolution.

    The dashboard's point-and-click editor writes these into
    ``analyzer_config`` under ``jewelry_handover`` / ``jewelry_tray`` /
    ``grab_and_run`` (see zone_router.save_high_value_counter). The edge
    agent decodes frames at whatever resolution the RTSP stream provides, so
    absolute pixel polygons never line up — sending normalized fractions lets
    the agent scale them per frame, exactly like the people-count / exclusion
    / inventory helpers above.
    """
    ac = getattr(c, "analyzer_config", None) or {}
    ref_w = float(getattr(c, "resolution_width", None) or 1920)
    ref_h = float(getattr(c, "resolution_height", None) or 1080)

    def norm_poly(points):
        if not isinstance(points, list) or len(points) < 3:
            return None
        pts: list[tuple[float, float]] = []
        for pt in points:
            try:
                x, y = float(pt[0]), float(pt[1])
            except (TypeError, IndexError, ValueError):
                continue
            pts.append((x, y))
        if len(pts) < 3:
            return None
        # Already normalized (legacy safety): every vertex within [0, 1].
        if max(x for x, _ in pts) <= 1.0 and max(y for _, y in pts) <= 1.0:
            return [[x, y] for x, y in pts]
        return [
            [max(0.0, min(1.0, x / ref_w)), max(0.0, min(1.0, y / ref_h))]
            for x, y in pts
        ]

    handover = ac.get("jewelry_handover") or {}
    tray_cfg = ac.get("jewelry_tray") or {}
    grab = ac.get("grab_and_run") or {}

    trays = []
    for t in tray_cfg.get("trays") or []:
        if not isinstance(t, dict):
            continue
        poly = norm_poly(t.get("polygon"))
        if poly is not None:
            trays.append({"label": str(t.get("label", "tray")), "polygon": poly})

    return {
        "jewelry_handover": {
            "counter_polygon": norm_poly(handover.get("counter_polygon")),
            "tray_polygon": norm_poly(handover.get("tray_polygon")),
            "min_hand_inside_frames": handover.get("min_hand_inside_frames", 2),
            "cooldown_seconds": handover.get("cooldown_seconds", 30.0),
            "confidence_threshold": handover.get("confidence_threshold", 0.45),
            "require_person_at_counter": handover.get("require_person_at_counter", True),
        },
        "jewelry_tray": {
            "counter_polygon": norm_poly(tray_cfg.get("counter_polygon")),
            "trays": trays,
            "drop_ratio_threshold": tray_cfg.get("drop_ratio_threshold", 0.25),
            "check_interval_seconds": tray_cfg.get("check_interval_seconds", 3.0),
            "cooldown_seconds": tray_cfg.get("cooldown_seconds", 30.0),
            "person_required": tray_cfg.get("person_required", True),
            "confidence_threshold": tray_cfg.get("confidence_threshold", 0.45),
        },
        "grab_and_run": {
            "case_polygon": norm_poly(grab.get("case_polygon")),
            "exit_polygon": norm_poly(grab.get("exit_polygon")),
            "approach_polygon": norm_poly(grab.get("approach_polygon")),
            "max_window_seconds": grab.get("max_window_seconds", 8.0),
            "min_exit_speed_px_s": grab.get("min_exit_speed_px_s", 120.0),
            "cooldown_seconds": grab.get("cooldown_seconds", 30.0),
            "confidence_threshold": grab.get("confidence_threshold", 0.45),
        },
    }


def _detection_toggles(c) -> dict:
    """Return the camera's per-analytic enable flags for the edge agent.

    Mirrors EXACTLY the resolution order used by ``ingest_event()``'s
    OPT_IN_EVENT_TYPES gate, so the agent's local decision and the
    backend's authoritative decision can never disagree:

      1. ``analyzer_config.detections.<key>`` — the dashboard toggle. If
         present it always wins (an owner switching a detection OFF must
         never be overridden by a stale feature block).
      2. ``analyzer_config.<key>.enabled`` — legacy per-feature flag.
      3. Otherwise OFF. These are opt-in behaviour heuristics; defaulting
         them ON is what used to flood the incident feed.
    """
    cfg = getattr(c, "analyzer_config", None) or {}
    detections_cfg = cfg.get("detections") or {}
    out: dict[str, bool] = {}
    for key in (
        "shoplifting",
        "loitering",
        "suspicious_behavior",
        "crowding",
        "fall_detected",
        "people_count",
    ):
        toggle = detections_cfg.get(key)
        if toggle is not None:
            out[key] = bool(toggle)
        else:
            out[key] = bool((cfg.get(key) or {}).get("enabled"))
    return out


# ---------------------------------------------------------------------------
# Live pipeline wiring (populated by main.py via set_pipeline) + snapshot store
# ---------------------------------------------------------------------------

# Populated by main.py via set_pipeline() — same shared instance used by
# demo_router / stores_router so edge incidents fan out to the live dashboard.
_pipeline = None  # type: ignore[assignment]

# Populated by main.py via set_webhook_engine() — same WebhookEngine instance
# used by pos_router, so edge detection events (shoplifting, tamper, etc.)
# can trigger outbound SMS/WhatsApp/Slack/Teams alerts.
_webhook_engine = None  # type: ignore[assignment]

# Snapshot root that snapshots_router serves at
# /api/snapshots/{tenant_id}/{camera_id}/{filename}
_SNAPSHOTS_ROOT = Path(__file__).resolve().parent.parent.parent / "snapshots"


def set_pipeline(p) -> None:  # type: ignore[no-untyped-def]
    global _pipeline  # noqa: PLW0603
    _pipeline = p


def set_webhook_engine(engine) -> None:  # type: ignore[no-untyped-def]
    """Inject the shared WebhookEngine so edge detection events can trigger
    outbound alerts (SMS/WhatsApp via Twilio, Slack, Teams, generic HTTP)."""
    global _webhook_engine  # noqa: PLW0603
    _webhook_engine = engine


# ---------------------------------------------------------------------------
# Live frame relay — in-memory latest-frame cache
# ---------------------------------------------------------------------------
# Cameras are almost always on a private LAN the cloud backend cannot reach
# directly (see cameras_router.test_camera_connection). The Edge Agent already
# opens the RTSP stream locally, so it pushes a low-fps JPEG frame here and
# cameras_router's /stream endpoint reads the latest one for that camera.
#
# Keyed by camera_id -> (jpeg_bytes, monotonic_timestamp, tenant_id).
# This remains a development fallback only. Production runs multiple Uvicorn
# workers, so the authoritative latest frame is stored in Redis below.
_latest_edge_frames: dict[str, tuple[bytes, float, str]] = {}
# Treat a frame as unavailable if older than this. Generous window (45s) so a
# brief uplink hiccup on the store's network degrades to a slightly stale
# preview instead of blanking the live tile entirely.
_FRAME_STALE_SEC = 45.0
_MAX_SNAPSHOT_BYTES = 2_000_000
_MAX_FRAME_BYTES = 1_000_000
_FRAME_REDIS_PREFIX = "vantag:live-frame:"
_frame_redis_client = None
_frame_redis_url = None


def _get_frame_redis():
    """Return a binary Redis client for the cross-worker frame relay.

    The normal bootstrap Redis client uses ``decode_responses=True`` and is
    deliberately kept separate because JPEG bytes must not be decoded as
    UTF-8. A short socket timeout makes Redis failure degrade to the local
    development cache instead of blocking camera/API requests.
    """
    global _frame_redis_client, _frame_redis_url  # noqa: PLW0603
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return None
    if _frame_redis_client is not None and _frame_redis_url == redis_url:
        return _frame_redis_client
    try:
        import redis as _redis

        _frame_redis_client = _redis.from_url(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=0.15,
            socket_timeout=0.15,
            health_check_interval=30,
        )
        _frame_redis_url = redis_url
        return _frame_redis_client
    except Exception:  # noqa: BLE001
        _frame_redis_client = None
        _frame_redis_url = None
        return None


def _frame_key(tenant_id: str, camera_id: str) -> str:
    return f"{_FRAME_REDIS_PREFIX}{tenant_id}:{camera_id}"


def _frame_ts_key(tenant_id: str, camera_id: str) -> str:
    return f"{_frame_key(tenant_id, camera_id)}:ts"


def _store_latest_edge_frame(tenant_id: str, camera_id: str, raw: bytes) -> None:
    """Store a frame in shared Redis and the local fallback cache."""
    now = time.time()
    _latest_edge_frames[camera_id] = (raw, time.monotonic(), str(tenant_id))
    redis_client = _get_frame_redis()
    if redis_client is None:
        return
    try:
        ttl = int(_FRAME_STALE_SEC + 5)
        pipe = redis_client.pipeline(transaction=True)
        pipe.setex(_frame_key(str(tenant_id), camera_id), ttl, raw)
        pipe.setex(_frame_ts_key(str(tenant_id), camera_id), ttl, str(now).encode())
        pipe.execute()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Shared frame relay unavailable; using local cache: %s", exc)


def get_latest_edge_frame_age(tenant_id: str, camera_id: str) -> float | None:
    """Return the age of a fresh frame, or None when no fresh frame exists."""
    redis_client = _get_frame_redis()
    if redis_client is not None:
        try:
            raw_ts = redis_client.get(_frame_ts_key(str(tenant_id), camera_id))
            raw_frame = redis_client.get(_frame_key(str(tenant_id), camera_id))
            if raw_ts is not None and raw_frame:
                age = max(0.0, time.time() - float(raw_ts.decode()))
                if age <= _FRAME_STALE_SEC:
                    return age
        except Exception as exc:  # noqa: BLE001
            logger.debug("Shared frame age lookup failed: %s", exc)

    entry = _latest_edge_frames.get(camera_id)
    if entry is None or str(entry[2]) != str(tenant_id):
        return None
    age = max(0.0, time.monotonic() - entry[1])
    return age if age <= _FRAME_STALE_SEC else None


def _is_safe_storage_component(value: str) -> bool:
    """Allow only a single path component for tenant/camera storage keys."""
    text = str(value)
    return bool(text) and text not in {".", ".."} and ".." not in text and "/" not in text and "\\" not in text


def get_latest_edge_frame(tenant_id: str, camera_id: str) -> bytes | None:
    """Return the latest tenant-scoped fresh frame across all workers."""
    redis_client = _get_frame_redis()
    if redis_client is not None:
        try:
            raw_frame = redis_client.get(_frame_key(str(tenant_id), camera_id))
            raw_ts = redis_client.get(_frame_ts_key(str(tenant_id), camera_id))
            if raw_frame and raw_ts:
                age = max(0.0, time.time() - float(raw_ts.decode()))
                if age <= _FRAME_STALE_SEC:
                    return raw_frame
        except Exception as exc:  # noqa: BLE001
            logger.debug("Shared frame lookup failed; using local cache: %s", exc)

    entry = _latest_edge_frames.get(camera_id)
    if entry is None:
        return None
    jpeg_bytes, ts, frame_tenant_id = entry
    if str(frame_tenant_id) != str(tenant_id):
        return None
    if (time.monotonic() - ts) > _FRAME_STALE_SEC:
        return None
    return jpeg_bytes


def _save_edge_snapshot(tenant_id: str, camera_id: str, b64: str) -> str | None:
    """Decode a base64 JPEG from the edge agent and persist it under the
    snapshots root so the JWT-scoped snapshots endpoint can serve it.

    Returns the public ``/api/snapshots/...`` URL, or None on failure.
    """
    if not b64 or not _is_safe_storage_component(camera_id):
        return None
    try:
        # Strip an optional data-URI prefix ("data:image/jpeg;base64,....")
        if "," in b64 and b64.strip().lower().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        raw = base64.b64decode(b64, validate=True)
        if len(raw) > _MAX_SNAPSHOT_BYTES or not raw.startswith(b"\xff\xd8\xff"):
            return None
        cam_dir = _SNAPSHOTS_ROOT / str(tenant_id) / str(camera_id)
        cam_dir.mkdir(parents=True, exist_ok=True)
        fname = f"{uuid.uuid4().hex}.jpg"
        (cam_dir / fname).write_bytes(raw)
        return f"/api/snapshots/{tenant_id}/{camera_id}/{fname}"
    except Exception:  # noqa: BLE001
        return None


async def _emit_edge_event(event: dict, store_id: str) -> None:
    """Fan a canonical edge event into the live pipeline, mirroring
    demo_router._inject(): recent_events + risk buffer + SQLite persist +
    WebSocket broadcast. No-op if the pipeline is not wired yet.
    """
    pipe = _pipeline
    if pipe is None:
        return
    event_type = event["type"]
    # Risk weight per event type (same scale demo_router uses)
    weights = {
        "face_match": 40, "shoplifting": 30, "tamper": 25,
        "fall_detected": 25, "fall": 25, "restricted_zone": 20,
        "loitering": 15, "inventory_movement": 10, "queue": 10,
        "queue_breach": 10,
    }
    weight = weights.get(event_type, 10)

    # 1) recent_events deque (read by stores_router.list_incidents)
    try:
        pipe.recent_events[store_id].appendleft(event)
    except Exception:  # noqa: BLE001
        pass
    # 2) risk-score buffer: (event_type, weight, monotonic) keyed by store_id
    try:
        async with pipe._event_buffer_lock:
            pipe._event_buffer[store_id].append(
                (event_type, weight, time.monotonic())
            )
    except Exception:  # noqa: BLE001
        pass
    # 3) persist to SQLite incident store (audit history)
    try:
        from ..db import incident_store as _istore  # lazy import

        await asyncio.to_thread(_istore.insert_incident, event)
    except Exception:  # noqa: BLE001
        pass
    # 4) WebSocket broadcast to the dashboard
    try:
        if pipe._ws_broadcast:
            tenant_id = event.get("tenant_id")
            if not tenant_id:
                logger.error("Refusing to broadcast edge event without tenant_id | incident=%s", event.get("incident_id"))
                return
            await pipe._ws_broadcast({
                "type":         "incident",
                "tenant_id":    tenant_id,
                "incident_id":  event["incident_id"],
                "store_id":     store_id,
                "camera_id":    event["camera_id"],
                "event_type":   event_type,
                "severity":     event["severity"],
                "description":  event["description"],
                "occurred_at":  event["timestamp"],
                "snapshot_url": event.get("snapshot_url"),
                "is_demo":      False,
            })
    except Exception:  # noqa: BLE001
        pass

# ---------------------------------------------------------------------------
# Bootstrap token store (Redis if available, in-memory fallback for dev)
# ---------------------------------------------------------------------------

_BOOTSTRAP_TTL_SECONDS = 15 * 60  # 15 minutes


def _get_redis():
    """Return a Redis client or None if Redis is not configured."""
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return None
    try:
        import redis as _redis
        return _redis.from_url(redis_url, decode_responses=True)
    except Exception:  # noqa: BLE001
        return None


# In-memory fallback for environments without Redis (dev / edge-only)
_bootstrap_tokens: dict[str, str] = {}  # token → tenant_id

# In-memory per-tenant "please run a LAN camera scan" flags. Single uvicorn
# process, so a plain dict is sufficient (mirrors _bootstrap_tokens). The agent
# consumes the flag on its next heartbeat.
_scan_requests: dict[str, bool] = {}  # tenant_id → scan_requested

# ---------------------------------------------------------------------------
# RTSP probe jobs — the cloud cannot reach private LAN IPs, so path probing
# (e.g. "auto-detect RTSP path" for Hikvision/Dahua/...) is delegated to the
# tenant's online Edge Agent. Jobs are queued here, delivered in the heartbeat
# response, and the agent POSTs the result back to /edge/rtsp-probe-result.
# ---------------------------------------------------------------------------
_rtsp_probe_jobs: dict[str, list[dict]] = {}    # tenant_id → queued jobs
_rtsp_probe_results: dict[str, dict] = {}       # job_id → result record
_PROBE_RESULT_TTL = 600  # seconds


def _prune_probe_results() -> None:
    cutoff = datetime.now(timezone.utc).timestamp() - _PROBE_RESULT_TTL
    stale = [k for k, v in _rtsp_probe_results.items() if v.get("_ts", 0) < cutoff]
    for k in stale:
        _rtsp_probe_results.pop(k, None)


def queue_rtsp_probe(tenant_id: str, ip: str, port: int = 554,
                     username: str | None = None, password: str | None = None,
                     brand: str | None = None) -> str:
    """Queue an agent-side RTSP path probe. Returns the job_id to poll."""
    _prune_probe_results()
    job_id = uuid.uuid4().hex
    _rtsp_probe_jobs.setdefault(tenant_id, []).append({
        "job_id": job_id, "ip": ip, "port": port,
        "username": username, "password": password, "brand": brand,
    })
    _rtsp_probe_results[job_id] = {
        "status": "pending",
        "_ts": datetime.now(timezone.utc).timestamp(),
    }
    return job_id


def consume_rtsp_probes(tenant_id: str) -> list[dict]:
    """Return (and clear) queued probe jobs for this tenant's agent."""
    return _rtsp_probe_jobs.pop(tenant_id, [])


def get_rtsp_probe_result(job_id: str) -> dict | None:
    return _rtsp_probe_results.get(job_id)


def request_camera_scan(tenant_id: str) -> None:
    """Mark that the given tenant's agent should run a discovery scan."""
    _scan_requests[tenant_id] = True


def consume_camera_scan(tenant_id: str) -> bool:
    """Return True (and clear) if a scan was requested for this tenant."""
    return _scan_requests.pop(tenant_id, False)


def _store_bootstrap_token(token: str, tenant_id: str) -> None:
    r = _get_redis()
    if r:
        r.setex(f"bootstrap:{token}", _BOOTSTRAP_TTL_SECONDS, tenant_id)
    else:
        _bootstrap_tokens[token] = tenant_id


def _consume_bootstrap_token(token: str) -> str | None:
    """Return tenant_id and delete the token (one-time use). Returns None if invalid."""
    r = _get_redis()
    if r:
        key = f"bootstrap:{token}"
        tenant_id = r.get(key)
        if tenant_id:
            r.delete(key)
        return tenant_id
    else:
        return _bootstrap_tokens.pop(token, None)


def generate_registration_token(tenant_id: str) -> str:
    """
    Generate a one-time registration token for an edge agent bootstrap.
    The token is stored with a 15-minute TTL and consumed on first use.
    Called from the onboarding/dashboard flow.
    """
    token = uuid.uuid4().hex
    _store_bootstrap_token(token, tenant_id)
    return token


async def _verify_agent(
    x_api_key: str = Header(..., alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> EdgeAgent:
    result = await session.execute(
        select(EdgeAgent).where(EdgeAgent.api_key == x_api_key)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return agent


class RegisterBody(BaseModel):
    device_type: str
    device_name: str | None = None
    os_version: str | None = None
    app_version: str | None = None
    capabilities: dict | None = None


class HeartbeatBody(BaseModel):
    camera_statuses: dict[str, str] | None = None  # camera_id → online/offline
    cpu_percent: float | None = None
    memory_percent: float | None = None
    fps_per_camera: dict[str, float] | None = None
    person_counts: dict[str, int] | None = None  # camera_id → live person count
    person_entries: dict[str, int] | None = None  # camera_id → cumulative visitors today (agent-side)
    agent_version: str | None = None
    # Detector status the agent verified from the loaded ONNX graph shape (NOT
    # from the filename — a cached file named yolo26n.onnx can contain a
    # YOLOv8 graph). Keys: architecture, model, expected_model, is_preferred,
    # ultralytics_version, acquire_error.
    model_status: dict | None = None
    pending_incidents: int | None = None  # durable agent outbox depth


# ---------------------------------------------------------------------------
# Live people-count store (SQLite-backed, shared across uvicorn workers)
# ---------------------------------------------------------------------------
# The Edge Agent reports per-camera person counts (from YOLO person detections)
# in every heartbeat. The backend runs with ``--workers 2`` (two separate OS
# processes), so an in-memory dict is NOT shared between the worker that
# receives the heartbeat POST and the worker that serves the dashboard GET —
# that was why the People Count page always showed 0. The store now lives in
# backend/db/people_count_store.py (SQLite, WAL mode) which is shared by all
# workers AND survives backend restarts/redeploys.

from ..db import people_count_store as _pc_store

_PERSON_COUNT_STALE_SEC = _pc_store.STALE_SEC


def _record_person_counts(tenant_id: str, counts: dict[str, int]) -> None:
    try:
        _pc_store.record_counts(tenant_id, counts)
    except Exception:  # noqa: BLE001 — never fail a heartbeat over count storage
        logger.exception("Failed to persist person counts for tenant %s", tenant_id)


class DetectionEventBody(BaseModel):
    camera_id: str
    event_type: str
    # Stable ID generated by the edge agent. Replayed requests return the
    # original event instead of creating a second incident.
    event_id: str | None = None
    severity: str = "medium"
    confidence: float | None = None
    risk_score: float | None = None
    location: str | None = None
    snapshot_b64: str | None = None
    person_crop_b64: str | None = None
    metadata: dict | None = None


class CountSnapshotBody(BaseModel):
    camera_id: str
    count: int
    snapshot_b64: str


# Fixed filename so each camera keeps exactly ONE annotated count snapshot on
# disk (overwritten in place) — no unbounded disk growth.
_COUNT_SNAPSHOT_NAME = "people_count_latest.jpg"
# Snapshot considered stale/hidden after this many seconds without an update.
_COUNT_SNAPSHOT_STALE_SEC = 300.0


def _count_snapshot_path(tenant_id: str, camera_id: str) -> Path:
    return _SNAPSHOTS_ROOT / str(tenant_id) / str(camera_id) / _COUNT_SNAPSHOT_NAME


@edge_router.post("/people-count-snapshot")
async def post_people_count_snapshot(
    body: CountSnapshotBody,
    agent: EdgeAgent = Depends(_verify_agent),
) -> dict:
    """Store the latest annotated people-count snapshot for a camera.

    The Edge Agent pushes a JPEG with green person bounding boxes drawn
    (rate-limited to one every ~20s) so the dashboard can show visual proof
    of what is being counted. One file per camera, overwritten in place.
    """
    b64 = body.snapshot_b64
    if not _is_safe_storage_component(body.camera_id):
        raise HTTPException(status_code=422, detail="Invalid camera_id")
    if len(b64) > 2_800_000:
        raise HTTPException(status_code=413, detail="Snapshot payload is too large")
    try:
        if "," in b64 and b64.strip().lower().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        raw = base64.b64decode(b64, validate=True)
        if len(raw) > _MAX_SNAPSHOT_BYTES or not raw.startswith(b"\xff\xd8\xff"):  # sanity cap: 2 MB
            raise HTTPException(status_code=413, detail="Snapshot too large")
        path = _count_snapshot_path(str(agent.tenant_id), body.camera_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001
        logger.exception("Failed to store count snapshot for %s", body.camera_id)
        raise HTTPException(status_code=500, detail="Failed to store snapshot")
    return {"ok": True}


@edge_router.post("/register")
async def register_agent(
    body: RegisterBody,
    agent: EdgeAgent = Depends(_verify_agent),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Called once when edge agent first starts. Returns camera configs."""
    await session.execute(
        update(EdgeAgent)
        .where(EdgeAgent.id == agent.id)
        .values(
            device_type=body.device_type,
            device_name=body.device_name,
            capabilities=body.capabilities,
            status="online",
            last_heartbeat=datetime.now(timezone.utc),
        )
    )
    # Get camera configs for this tenant
    result = await session.execute(
        select(CameraConfig)
        .where(CameraConfig.tenant_id == agent.tenant_id, CameraConfig.enabled == True)
    )
    cameras = result.scalars().all()
    await session.commit()

    return {
        "agent_id": agent.id,
        "tenant_id": agent.tenant_id,
        "cameras": [
            {
                "camera_id": c.camera_id,
                "rtsp_url": c.get_rtsp_url() if hasattr(c, "get_rtsp_url") else c.rtsp_url,
                "name": c.name,
                "location": c.location,
                "fps_target": c.fps_target,
                "resolution_width": c.resolution_width,
                "resolution_height": c.resolution_height,
                "people_count_zones": _normalized_people_count_zones(c),
                "exclusion_zones": _normalized_exclusion_zones(c),
                "inventory_zones": _normalized_inventory_zones(c),
                "high_value_counter": _normalized_high_value_counter(c),
                # Per-camera opt-in analytic toggles. Previously NOT sent at
                # all, so the agent ran every behaviour heuristic (pose
                # shoplifting, loitering, crowding, suspicious, fall) on every
                # camera and relied entirely on ingest_event()'s
                # OPT_IN_EVENT_TYPES gate to throw the results away. That
                # burned CPU on all cameras and, worse, made a test in front
                # of a camera where the analytic is OFF look identical to a
                # broken detector (event sent, silently dropped server-side).
                "detections": _detection_toggles(c),
            }
            for c in cameras
        ],
    }


@edge_router.post("/heartbeat")
async def heartbeat(
    body: HeartbeatBody,
    agent: EdgeAgent = Depends(_verify_agent),
    session: AsyncSession = Depends(get_session),
) -> dict:
    now = datetime.now(timezone.utc)
    await session.execute(
        update(EdgeAgent)
        .where(EdgeAgent.id == agent.id)
        .values(status="online", last_heartbeat=now)
    )
    # Update camera connection statuses
    if body.camera_statuses:
        for cam_id, cam_status in body.camera_statuses.items():
            await session.execute(
                update(CameraConfig)
                .where(
                    CameraConfig.tenant_id == agent.tenant_id,
                    CameraConfig.camera_id == cam_id,
                )
                .values(conn_status=cam_status, last_connected_at=now if cam_status == "online" else None)
            )
    # Record live per-camera person counts (in-memory footfall store)
    if body.person_counts:
        _record_person_counts(str(agent.tenant_id), body.person_counts)
    # Accumulate cumulative daily visitor entries (survives agent restarts)
    if body.person_entries:
        try:
            _pc_store.record_entries(str(agent.tenant_id), body.person_entries)
        except Exception:  # noqa: BLE001 — never fail a heartbeat over entry storage
            logger.exception("Failed to persist person entries for tenant %s", agent.tenant_id)
    # Record which detector this agent actually verified from its ONNX graph,
    # and alert the administrator if it silently fell back off YOLO26. Before
    # this, a fallback was only a local log.warning on the customer's laptop —
    # invisible to us and to them, so degraded accuracy went unnoticed.
    if body.model_status:
        try:
            from ..db import system_health_store as _sh_store

            _sh_store.record_agent_model_status(
                str(agent.tenant_id),
                str(agent.id),
                body.agent_version or "",
                body.model_status,
            )
            from ..services.system_health import clear_fault, report_fault

            if body.model_status.get("is_preferred") is False:
                arch = body.model_status.get("architecture") or "unknown"
                expected = body.model_status.get("expected_model") or "yolo26n"
                await report_fault(
                    component="model_fallback",
                    summary=(
                        f"Edge Agent detector fell back to {arch} "
                        f"(expected {expected})"
                    ),
                    detail=(
                        f"agent_id={agent.id}\n"
                        f"agent_version={body.agent_version}\n"
                        f"verified_architecture={arch}\n"
                        f"model_file={body.model_status.get('model')}\n"
                        f"onnx_output_shape={body.model_status.get('onnx_output_shape')}\n"
                        f"ultralytics={body.model_status.get('ultralytics')}\n"
                        f"acquire_error={body.model_status.get('acquire_error')}"
                    ),
                    tenant_id=str(agent.tenant_id),
                )
            elif body.model_status.get("is_preferred") is True:
                clear_fault("model_fallback")
        except Exception:  # noqa: BLE001 — never fail a heartbeat over telemetry
            logger.exception(
                "Failed to record agent model status for agent %s", agent.id
            )
    await session.commit()
    return {
        "ok": True,
        "server_time": now.isoformat(),
        "scan_requested": consume_camera_scan(agent.tenant_id),
        "rtsp_probe_jobs": consume_rtsp_probes(agent.tenant_id),
        "pending_incidents": body.pending_incidents,
    }


class FramePushBody(BaseModel):
    camera_id: str
    frame_b64: str


@edge_router.post("/frame")
async def push_frame(
    body: FramePushBody,
    agent: EdgeAgent = Depends(_verify_agent),
) -> dict:
    """Receive a low-fps JPEG frame from the Edge Agent for live preview.

    The cloud backend cannot reach camera RTSP URLs on a private LAN, so the
    on-site Edge Agent (which already has the stream open locally) pushes a
    frame every ~200ms. The most recent frame per camera is kept in memory
    and served by cameras_router's ``/stream`` endpoint. This is best-effort
    and intentionally lightweight — no retries, no persistence.
    """
    b64 = body.frame_b64
    if not b64 or not _is_safe_storage_component(body.camera_id):
        return {"ok": False}
    if len(b64) > 1_400_000:
        return {"ok": False}
    try:
        if "," in b64 and b64.strip().lower().startswith("data:"):
            b64 = b64.split(",", 1)[1]
        raw = base64.b64decode(b64, validate=True)
        if len(raw) > _MAX_FRAME_BYTES or not raw.startswith(b"\xff\xd8\xff"):
            return {"ok": False}
    except Exception:  # noqa: BLE001
        return {"ok": False}
    _store_latest_edge_frame(str(agent.tenant_id), body.camera_id, raw)
    return {"ok": True}


class RtspProbeResultBody(BaseModel):
    job_id: str
    success: bool
    rtsp_path: str | None = None
    rtsp_url: str | None = None
    brand: str | None = None
    tried_paths: list[str] | None = None
    error: str | None = None


@edge_router.post("/rtsp-probe-result")
async def rtsp_probe_result(
    body: RtspProbeResultBody,
    agent: EdgeAgent = Depends(_verify_agent),
) -> dict:
    """Edge Agent reports the outcome of an RTSP path probe job."""
    rec = _rtsp_probe_results.get(body.job_id)
    if rec is None:
        # Unknown/expired job — accept silently so the agent doesn't retry.
        return {"ok": True, "known": False}
    rec.update({
        "status": "done",
        "success": body.success,
        "rtsp_path": body.rtsp_path,
        "rtsp_url": body.rtsp_url,
        "brand": body.brand,
        "tried_paths": body.tried_paths or [],
        "error": body.error,
        "_ts": datetime.now(timezone.utc).timestamp(),
    })
    return {"ok": True, "known": True}


class DiscoveredCameraItem(BaseModel):
    ip: str
    port: int = 554
    brand: str | None = None
    model: str | None = None
    rtsp_path: str | None = None
    rtsp_url: str | None = None
    thumbnail_b64: str | None = None
    onvif: bool = False
    confidence: float | None = None
    needs_credentials: bool = False
    used_default_credential: bool = False


class DiscoveredCamerasBody(BaseModel):
    cameras: list[DiscoveredCameraItem] = []


@edge_router.post("/cameras/discovered")
async def ingest_discovered_cameras(
    body: DiscoveredCamerasBody,
    agent: EdgeAgent = Depends(_verify_agent),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Receive LAN-discovered cameras from the edge agent and upsert them as
    ``CameraConfig`` rows (``enabled=False`` — awaiting user confirmation).

    The agent runs the scan on the tenant's private store network; the backend
    persists the results so they surface in the dashboard's auto-detected list.
    """
    upserted = 0
    for cam in body.cameras:
        if not cam.ip:
            continue
        camera_id = "disc-" + cam.ip.replace(".", "-")

        # Save the thumbnail (if any) so the dashboard can render a preview.
        thumb_url = None
        if cam.thumbnail_b64:
            thumb_url = _save_edge_snapshot(agent.tenant_id, camera_id, cam.thumbnail_b64)

        frame_ok = bool(cam.rtsp_url and cam.thumbnail_b64)
        probe = {
            "port": cam.port,
            "rtsp_path": cam.rtsp_path,
            "onvif": cam.onvif,
            "confidence": cam.confidence,
            "needs_credentials": cam.needs_credentials,
            "used_default_credential": cam.used_default_credential,
            "thumbnail_url": thumb_url,
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        }

        existing = (
            await session.execute(
                select(CameraConfig).where(
                    CameraConfig.tenant_id == agent.tenant_id,
                    CameraConfig.camera_id == camera_id,
                )
            )
        ).scalar_one_or_none()

        if existing is None:
            row = CameraConfig(
                tenant_id=agent.tenant_id,
                camera_id=camera_id,
                name=cam.brand or f"Camera {cam.ip}",
                ip_address=cam.ip,
                brand=cam.brand,
                model=cam.model,
                conn_status="online" if frame_ok else "pending",
                probe_result=probe,
                enabled=False,
            )
            if cam.rtsp_url:
                row.set_rtsp_url(cam.rtsp_url)
            session.add(row)
            upserted += 1
        else:
            # Only refresh discovery metadata; never override an already
            # user-confirmed (enabled) camera's connection details.
            existing.ip_address = cam.ip
            if cam.brand:
                existing.brand = cam.brand
            if cam.model:
                existing.model = cam.model
            existing.probe_result = probe
            if not existing.enabled:
                existing.conn_status = "online" if frame_ok else "pending"
                if cam.rtsp_url:
                    existing.set_rtsp_url(cam.rtsp_url)
            upserted += 1

    await session.commit()
    logger.info(
        "Edge agent reported %d discovered camera(s) | tenant=%s",
        upserted, agent.tenant_id,
    )
    return {"ok": True, "upserted": upserted}


@edge_router.post("/events")
async def ingest_event(
    body: DetectionEventBody,
    agent: EdgeAgent = Depends(_verify_agent),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Receive a detection event from the edge agent and fan it out to the
    live dashboard pipeline (recent_events + risk buffer + SQLite + WebSocket).
    """
    camera = None
    try:
        camera = (
            await session.execute(
                select(CameraConfig).where(
                    CameraConfig.tenant_id == agent.tenant_id,
                    CameraConfig.camera_id == body.camera_id,
                )
            )
        ).scalar_one_or_none()
    except Exception:
        camera = None

    event_type = body.event_type.strip().lower()
    if not event_type or len(event_type) > 50:
        raise HTTPException(status_code=422, detail="event_type is invalid")
    if body.snapshot_b64 and len(body.snapshot_b64) > 2_800_000:
        raise HTTPException(status_code=413, detail="snapshot payload is too large")
    if body.person_crop_b64 and len(body.person_crop_b64) > 2_800_000:
        raise HTTPException(status_code=413, detail="person crop payload is too large")
    event_id = (body.event_id or "").strip() or str(uuid.uuid4())
    if len(event_id) > 36:
        raise HTTPException(status_code=422, detail="event_id is too long")
    if isinstance(body.metadata, dict):
        try:
            if len(json.dumps(body.metadata, separators=(",", ":"))) > 128_000:
                raise HTTPException(status_code=413, detail="metadata is too large")
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="metadata must be JSON serializable")

    # Idempotency: the edge client may retry after a timeout even though the
    # first request already committed. Return the existing event for this
    # tenant instead of running VLM, persistence, and alert dispatch twice.
    existing_event = (
        await session.execute(
            select(DetectionEvent).where(
                DetectionEvent.id == event_id,
                DetectionEvent.tenant_id == agent.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if existing_event is not None:
        return {"ok": True, "duplicate": True, "event_id": event_id}

    # A camera that the owner disabled entirely must not produce ANY
    # incidents — drop every event from it, regardless of type.
    if camera is not None and getattr(camera, "enabled", True) is False:
        logger.info(
            "Ignored event from disabled camera | tenant=%s camera=%s type=%s",
            agent.tenant_id,
            body.camera_id,
            event_type,
        )
        return {
            "ok": True,
            "ignored": True,
            "reason": "camera is disabled",
        }

    analyzer_config = (getattr(camera, "analyzer_config", None) or {}) if camera else {}
    configured_zones = {
        "inventory_movement": (analyzer_config.get("inventory_movement") or {}).get("zones") or [],
        "restricted_zone": (analyzer_config.get("restricted_zone") or {}).get("restricted_zones") or [],
        "queue_breach": (analyzer_config.get("queue_length") or {}).get("queue_zones") or [],
        "queue_length": (analyzer_config.get("queue_length") or {}).get("queue_zones") or [],
        # High-Value Counter detectors only fire once their polygons are
        # drawn (the editor writes jewelry_handover / jewelry_tray /
        # grab_and_run into analyzer_config). Gating here mirrors the edge
        # agent's own no-polygon → no-event behaviour, so a misconfigured
        # camera can never produce a jewellery event server-side either.
        "jewelry_handover": (analyzer_config.get("jewelry_handover") or {}).get("tray_polygon") or [],
        "jewelry_tray": (analyzer_config.get("jewelry_tray") or {}).get("trays") or [],
        "grab_and_run": (analyzer_config.get("grab_and_run") or {}).get("case_polygon") or [],
    }
    if event_type in configured_zones and not configured_zones[event_type]:
        logger.info(
            "Ignored unconfigured edge event | tenant=%s camera=%s type=%s",
            agent.tenant_id,
            body.camera_id,
            event_type,
        )
        return {
            "ok": True,
            "ignored": True,
            "reason": f"{event_type} has no configured zone",
        }

    # Behaviour-heuristic events (fired by the edge agent for ANY detected
    # person) must be explicitly enabled per camera before they are accepted.
    # Without this gate the agent's motion heuristics flood the incident feed
    # with false "shoplifting"/"loitering"/"suspicious behaviour" reports even
    # though the shop owner never configured those detections.
    OPT_IN_EVENT_TYPES = {
        "shoplifting",
        "loitering",
        "suspicious_behavior",
        "suspicious_behaviour",
        "crowding",
        "fall_detected",
    }
    if event_type in OPT_IN_EVENT_TYPES:
        # Normalise UK/US spelling to a single config key.
        cfg_key = (
            "suspicious_behavior"
            if event_type == "suspicious_behaviour"
            else event_type
        )
        detections_cfg = analyzer_config.get("detections") or {}
        feature_cfg = analyzer_config.get(cfg_key) or {}
        toggle = detections_cfg.get(cfg_key)
        if toggle is not None:
            # An explicit per-camera toggle ALWAYS wins — a stale
            # feature-level "enabled" flag must never resurrect a
            # detection the owner switched OFF in the dashboard.
            enabled = bool(toggle)
        else:
            enabled = bool(feature_cfg.get("enabled"))
        if not enabled:
            logger.info(
                "Ignored non-enabled edge event | tenant=%s camera=%s type=%s",
                agent.tenant_id,
                body.camera_id,
                event_type,
            )
            return {
                "ok": True,
                "ignored": True,
                "reason": f"{event_type} detection is not enabled for this camera",
            }

    # Detection schedule: the owner may restrict AI detections to a daily
    # time window. Theft (shoplifting) is deliberately EXEMPT — it stays
    # live 24/7 regardless of the schedule.
    if event_type not in ("shoplifting", "theft"):
        schedule = analyzer_config.get("detection_schedule") or {}
        if schedule.get("enabled"):
            try:
                # NOTE: do NOT locally import `datetime` here — `datetime`
                # is already imported at module scope (see top of file) and
                # a local `from datetime import datetime` makes `datetime`
                # a local variable for this ENTIRE function (Python's
                # scoping rules apply per-function, not per-branch), which
                # raises UnboundLocalError for any call that skips this
                # branch (e.g. shoplifting/theft events, which intentionally
                # bypass the schedule check below) but still references the
                # module-level `datetime` further down in the function.
                from datetime import timedelta

                offset_min = int(schedule.get("tz_offset_minutes") or 0)
                local_now = datetime.now(timezone.utc) + timedelta(minutes=offset_min)
                now_hm = local_now.strftime("%H:%M")
                start = str(schedule.get("start") or "00:00")
                end = str(schedule.get("end") or "23:59")
                if start <= end:
                    in_window = start <= now_hm <= end
                else:
                    # Overnight window, e.g. 20:00 -> 06:00
                    in_window = now_hm >= start or now_hm <= end
            except Exception:  # noqa: BLE001
                in_window = True  # malformed schedule must never block events
            if not in_window:
                logger.info(
                    "Ignored out-of-schedule edge event | tenant=%s camera=%s type=%s window=%s-%s",
                    agent.tenant_id, body.camera_id, event_type,
                    schedule.get("start"), schedule.get("end"),
                )
                return {
                    "ok": True,
                    "ignored": True,
                    "reason": f"{event_type} is outside the configured detection schedule",
                }

    # 1) Decode + persist the snapshot JPEG so the dashboard can display it.
    snapshot_url = None
    if body.snapshot_b64:
        snapshot_url = _save_edge_snapshot(
            agent.tenant_id, body.camera_id, body.snapshot_b64
        )

    # 2) Resolve the store the dashboard keys incidents by.
    #    This used to slugify camera.location inline, splitting ONLY on the
    #    en-dash while cameras_router/stores_router split on en-dash AND
    #    hyphen — so the same camera produced two different store ids and its
    #    incidents landed under a store the dashboard never showed. Now it
    #    goes through CameraConfig.effective_store_id, the single definition.
    location = body.location
    site_id = None
    if camera is not None:
        if location is None:
            try:
                location = camera.location
            except Exception:  # noqa: BLE001
                location = None
        site_id = getattr(camera, "site_id", None)

    if camera is not None:
        try:
            store_id = camera.effective_store_id
        except Exception:  # noqa: BLE001
            store_id = derive_legacy_store_id(location)
    else:
        store_id = derive_legacy_store_id(location)

    # 2b) Staff face suppression: the edge agent attaches a native-resolution
    #     person crop to person-centric events. Match it against the enrolled
    #     Staff Faces / Watchlist embeddings; when the person is enrolled as
    #     STAFF the event is audited (record_match) but NOT persisted and NO
    #     alert is dispatched. Non-staff watchlist hits (banned/suspect) are
    #     recorded as watchlist matches and the event proceeds with enriched
    #     metadata.
    face_match = None
    if body.person_crop_b64 and staff_face_service.is_available():
        try:
            face_match = await asyncio.to_thread(
                staff_face_service.match_face_b64,
                body.person_crop_b64,
                str(agent.tenant_id),
            )
        except Exception:  # noqa: BLE001
            logger.exception("Staff face matching failed for camera %s", body.camera_id)
            face_match = None
    if face_match:
        try:
            record_match(
                entry_id=face_match["entry_id"],
                camera_id=body.camera_id,
                store_id=store_id,
                confidence=face_match["similarity"],
                snapshot_url=snapshot_url,
                tenant_id=str(agent.tenant_id),
            )
        except Exception:  # noqa: BLE001
            logger.exception("record_match failed for entry %s", face_match["entry_id"])
        if face_match.get("alert_level") == "staff":
            logger.info(
                "Suppressed %s event — recognised staff '%s' (sim=%.2f) | tenant=%s camera=%s",
                event_type, face_match["name"], face_match["similarity"],
                agent.tenant_id, body.camera_id,
            )
            return {
                "ok": True,
                "suppressed": True,
                "reason": f"recognised staff: {face_match['name']}",
                "similarity": face_match["similarity"],
            }
        # Known non-staff watchlist person — keep the event, tag identity.
        body.metadata = {
            **(body.metadata or {}),
            "watchlist_match": {
                "name": face_match["name"],
                "alert_level": face_match["alert_level"],
                "similarity": face_match["similarity"],
            },
        }

    # 2c) VLM verification (Tier 3, v1.5.2): for event types where a single
    #     still frame can plausibly confirm/refute the claim, cross-check the
    #     snapshot against a vision-language model before dispatching any
    #     SMS/WhatsApp/email/webhook alert. Fails open — if verification is
    #     disabled, unreachable, or errors, `vlm_result` stays None and the
    #     alert dispatches exactly as before. The incident itself is ALWAYS
    #     persisted and shown on the dashboard regardless of the verdict; only
    #     outbound alert dispatch (step 5/6 below) is gated on a confident
    #     "does not match" verdict.
    vlm_result: dict | None = None
    skip_alert_dispatch = False
    if snapshot_url and body.snapshot_b64 and vlm_verification_service.is_verifiable_event(event_type):
        try:
            raw_snapshot = body.snapshot_b64
            if "," in raw_snapshot and raw_snapshot.strip().lower().startswith("data:"):
                raw_snapshot = raw_snapshot.split(",", 1)[1]
            snapshot_bytes = base64.b64decode(raw_snapshot)

            # inventory_movement candidates come with a baseline ("before
            # the change") crop and the current ("after") crop attached by
            # the edge agent's InventoryMovementDetector — a direct
            # before/after comparison is materially more accurate than
            # judging a single still frame, so prefer it when available.
            ref_b64 = cur_b64 = None
            baseline_product_count = current_product_count = None
            if event_type == "inventory_movement" and isinstance(body.metadata, dict):
                ref_b64 = body.metadata.get("reference_snapshot_b64")
                cur_b64 = body.metadata.get("current_crop_b64")
                # Tier 2 (optional): open-vocabulary product counts computed
                # by the edge agent on both crops, when its detector is
                # available — enriches the VLM prompt with concrete numbers.
                baseline_product_count = body.metadata.get("baseline_product_count")
                current_product_count = body.metadata.get("current_product_count")

            def _decode(b64: str) -> bytes:
                if "," in b64 and b64.strip().lower().startswith("data:"):
                    b64 = b64.split(",", 1)[1]
                return base64.b64decode(b64)

            if ref_b64 and cur_b64:
                vlm_result = await vlm_verification_service.verify_inventory_change(
                    _decode(ref_b64), _decode(cur_b64),
                    baseline_product_count=baseline_product_count,
                    current_product_count=current_product_count,
                )
            else:
                vlm_result = await vlm_verification_service.verify_incident(event_type, snapshot_bytes)
        except Exception:  # noqa: BLE001 — verification must never break ingestion
            logger.exception("VLM verification threw for event %s camera %s", event_type, body.camera_id)
            vlm_result = None
        if vlm_result is not None and not vlm_result["matches"] and vlm_result["confidence"] >= 0.5:
            skip_alert_dispatch = True
            logger.info(
                "VLM verification rejected event | tenant=%s camera=%s type=%s confidence=%.2f reason=%s",
                agent.tenant_id, body.camera_id, event_type,
                vlm_result["confidence"], vlm_result["reasoning"],
            )
        # Drop the (large) raw comparison crops before persisting — they've
        # already served their purpose for verification and would otherwise
        # bloat every stored incident's metadata blob. The person snapshot
        # (if any) is saved as a file below and replaced with a URL instead.
        raw_person_b64 = (body.metadata or {}).get("person_snapshot_b64")
        clean_metadata = {
            k: v for k, v in (body.metadata or {}).items()
            if k not in ("reference_snapshot_b64", "current_crop_b64", "person_snapshot_b64")
        }
        body.metadata = {**clean_metadata, "vlm_verification": vlm_result}
        if raw_person_b64:
            person_url = _save_edge_snapshot(agent.tenant_id, body.camera_id, raw_person_b64)
            if person_url:
                body.metadata["person_snapshot_url"] = person_url

    # 3) Persist the audit row in the per-tenant detection_events table.
    event = DetectionEvent(
        id=event_id,
        tenant_id=agent.tenant_id,
        camera_id=body.camera_id,
        edge_agent_id=agent.id,
        event_type=body.event_type,
        severity=body.severity,
        confidence=body.confidence,
        risk_score=body.risk_score,
        location=location,
        site_id=site_id,
        snapshot_url=snapshot_url,
        event_meta=body.metadata,
    )
    session.add(event)
    try:
        await session.commit()
    except IntegrityError:
        # Two retries can arrive concurrently. The database primary key is
        # the final idempotency guard; only treat it as a duplicate when the
        # conflicting ID belongs to this tenant. A collision with another
        # tenant is rejected without exposing that tenant's event.
        await session.rollback()
        existing_event = (
            await session.execute(
                select(DetectionEvent).where(
                    DetectionEvent.id == event_id,
                    DetectionEvent.tenant_id == agent.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if existing_event is not None:
            return {"ok": True, "duplicate": True, "event_id": event_id}
        raise HTTPException(status_code=409, detail="event_id is already in use")

    # 4) Build the canonical incident dict and fan it into the live pipeline.
    description = (
        (body.metadata or {}).get("description")
        if isinstance(body.metadata, dict)
        else None
    ) or f"{body.event_type.replace('_', ' ').title()} detected on {body.camera_id}"
    incident = {
        "id": event.id,
        "incident_id": event.id,
        "tenant_id": str(agent.tenant_id),
        "type": body.event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "store_id": store_id,
        "camera_id": body.camera_id,
        "severity": body.severity,
        "confidence": body.confidence,
        "risk_score": body.risk_score,
        "description": description,
        "snapshot_url": snapshot_url,
        "metadata": {
            **(body.metadata or {}),
            "source": "edge_agent",
        },
        "acknowledged": False,
        "is_demo": False,
    }
    try:
        await _emit_edge_event(incident, store_id)
    except Exception:  # noqa: BLE001
        pass

    # 5) Fan the incident out to any matching outbound alert subscriptions
    #    (SMS/WhatsApp via Twilio, Slack, Teams, generic HTTP) — fire-and-forget
    #    so a slow/unreachable webhook endpoint never delays the agent's response.
    #    Skipped only when VLM verification confidently rejected the event
    #    (the incident record above is unaffected — it's still on the dashboard).
    if _webhook_engine is not None and not skip_alert_dispatch:
        try:
            from ..utils.background_tasks import fire_and_forget
            fire_and_forget(_webhook_engine.dispatch(incident), name=f"webhook_dispatch_{event.id}")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to schedule webhook dispatch for event %s", event.id)

    # 6) Fan the incident out to the tenant's own Alert Dispatch settings
    #    (SMS/WhatsApp via their own Twilio creds, Email) — configured from
    #    Account > Alert Dispatch. Independent of the platform webhooks.yaml.
    if not skip_alert_dispatch:
        try:
            tenant_alert_settings = (
                await session.execute(select(Tenant.alert_settings).where(Tenant.id == agent.tenant_id))
            ).scalar_one_or_none()
            if tenant_alert_settings:
                from ..utils.background_tasks import fire_and_forget
                fire_and_forget(dispatch_tenant_alert(tenant_alert_settings, incident), name=f"tenant_alert_{event.id}")
        except Exception:  # noqa: BLE001
            logger.exception("Failed to schedule tenant alert dispatch for event %s", event.id)

    return {"ok": True, "event_id": event.id, "vlm_verification": vlm_result}


@edge_router.get("/config")
async def get_config(
    agent: EdgeAgent = Depends(_verify_agent),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Edge agent polls this to get latest camera configs.

    Multi-store scoping: if this agent is pinned to a site, it only receives
    that site's cameras. An unpinned agent (``site_id`` NULL — every existing
    install) still receives all tenant cameras, so this deploy changes nothing
    for single-store customers.
    """
    stmt = (
        select(CameraConfig)
        .where(CameraConfig.tenant_id == agent.tenant_id, CameraConfig.enabled == True)
    )
    agent_site = getattr(agent, "site_id", None)
    if agent_site:
        stmt = stmt.where(CameraConfig.site_id == agent_site)
    result = await session.execute(stmt)
    cameras = result.scalars().all()

    # Door-relay configuration (door_control) is tenant-scoped and edited via
    # the relay setup wizard. The agent applies it to its MQTT relay driver.
    tenant = await session.get(Tenant, agent.tenant_id)
    door_control = (tenant.relay_settings or {}) if tenant else {}

    return {
        "door_control": door_control,
        "cameras": [
            {
                "camera_id": c.camera_id,
                "rtsp_url": c.get_rtsp_url() if hasattr(c, "get_rtsp_url") else c.rtsp_url,
                "name": c.name,
                "location": c.location,
                "fps_target": c.fps_target,
                "confidence_threshold": (getattr(c, "analyzer_config", None) or {}).get("confidence_threshold"),
                "people_count_zones": _normalized_people_count_zones(c),
                "exclusion_zones": _normalized_exclusion_zones(c),
                "inventory_zones": _normalized_inventory_zones(c),
                "high_value_counter": _normalized_high_value_counter(c),
                # Per-camera opt-in analytic toggles. Previously NOT sent at
                # all, so the agent ran every behaviour heuristic (pose
                # shoplifting, loitering, crowding, suspicious, fall) on every
                # camera and relied entirely on ingest_event()'s
                # OPT_IN_EVENT_TYPES gate to throw the results away. That
                # burned CPU on all cameras and, worse, made a test in front
                # of a camera where the analytic is OFF look identical to a
                # broken detector (event sent, silently dropped server-side).
                "detections": _detection_toggles(c),
            }
            for c in cameras
        ]
    }


@edge_router.get("/agents")
async def list_agents(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Return all EdgeAgent rows for the calling tenant with derived live status.

    ``effective_status`` is ``"online"`` only when ``last_heartbeat`` is within
    the last 5 minutes; otherwise ``"offline"``.  This avoids a background
    cron job to flip the DB column and is always accurate at read time.
    """
    from datetime import timedelta

    tenant_id = user["tenant_id"]
    result = await session.execute(
        select(EdgeAgent).where(EdgeAgent.tenant_id == tenant_id)
    )
    agents = result.scalars().all()
    now = datetime.now(timezone.utc)
    stale_threshold = timedelta(minutes=5)

    model_status_by_agent: dict[str, dict] = {}
    try:
        from ..db import system_health_store as _sh_store

        model_status_by_agent = {
            str(row["agent_id"]): row
            for row in _sh_store.list_agent_model_status(tenant_id)
        }
    except Exception:  # noqa: BLE001 — status panel must remain available
        logger.exception("Failed to load agent model telemetry")

    items = []
    for a in agents:
        if a.last_heartbeat is not None:
            hb = a.last_heartbeat
            # Ensure tz-aware comparison
            if hb.tzinfo is None:
                from datetime import timezone as _tz
                hb = hb.replace(tzinfo=_tz.utc)
            age = now - hb
            effective_status = "online" if age <= stale_threshold else "offline"
            last_heartbeat_iso = hb.isoformat()
            last_heartbeat_age_seconds = int(age.total_seconds())
        else:
            effective_status = "offline"
            last_heartbeat_iso = None
            last_heartbeat_age_seconds = None

        telemetry = model_status_by_agent.get(str(a.id))
        items.append({
            "agent_id": a.id,
            "device_type": a.device_type,
            "device_name": a.device_name or a.device_type,
            "status": effective_status,
            "last_heartbeat": last_heartbeat_iso,
            "last_heartbeat_age_seconds": last_heartbeat_age_seconds,
            "camera_count": a.camera_count,
            "capabilities": a.capabilities,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "model_status": telemetry.get("status") if telemetry else None,
            "model_status_age_seconds": telemetry.get("age_seconds") if telemetry else None,
            "model_status_stale": telemetry.get("stale") if telemetry else True,
        })

    return {"agents": items, "total": len(items)}


@edge_router.get("/people-counts")
async def get_people_counts(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Live per-camera person counts + rolling 24h hourly peak history.

    Counts are pushed by the Edge Agent in every heartbeat (YOLO person
    detections per camera). A camera's count is considered stale if no
    heartbeat arrived within the last 2 minutes. Cameras whose People Count
    toggle (CameraView > AI Detections) is switched off are excluded.
    """
    tenant_id = str(user["tenant_id"])
    now = time.time()
    try:
        latest = _pc_store.get_latest_counts(tenant_id)
        peak_rows = _pc_store.get_hourly_peaks(tenant_id, hours=24)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to read people-count store")
        latest, peak_rows = [], []
    try:
        daily_entries = _pc_store.get_daily_entries(tenant_id)
    except Exception:  # noqa: BLE001
        daily_entries = {}

    # Per-camera People Count toggle (default ON when never set).
    disabled_cams: set[str] = set()
    try:
        rows = await session.execute(
            select(CameraConfig).where(CameraConfig.tenant_id == user["tenant_id"])
        )
        for c in rows.scalars().all():
            det = ((getattr(c, "analyzer_config", None) or {}).get("detections") or {})
            if det.get("people_count") is False:
                disabled_cams.add(c.camera_id)
    except Exception:  # noqa: BLE001 — never break live counts on a DB hiccup
        pass

    cameras = []
    total = 0
    for cam_id, count, ts in latest:
        if cam_id in disabled_cams:
            continue
        age = now - ts
        stale = age > _PERSON_COUNT_STALE_SEC
        if not stale:
            total += count
        # Latest annotated count snapshot (green boxes) pushed by the agent.
        snapshot_url = None
        try:
            snap = _count_snapshot_path(tenant_id, cam_id)
            if snap.exists():
                mtime = snap.stat().st_mtime
                if (now - mtime) <= _COUNT_SNAPSHOT_STALE_SEC:
                    snapshot_url = (
                        f"/api/snapshots/{tenant_id}/{cam_id}/{_COUNT_SNAPSHOT_NAME}"
                        f"?t={int(mtime)}"
                    )
        except Exception:  # noqa: BLE001
            pass
        cameras.append({
            "camera_id": cam_id,
            "person_count": count,
            "entries_today": int(daily_entries.get(cam_id, 0)),
            "age_seconds": int(age),
            "stale": stale,
            "snapshot_url": snapshot_url,
        })

    history = [
        {"hour": h, "peak_count": c}
        for h, c in peak_rows
    ]

    total_entries = sum(
        v for k, v in daily_entries.items() if k not in disabled_cams
    )

    return {
        "total_people": total,
        "total_entries_today": total_entries,
        "cameras": cameras,
        "hourly_peaks": history,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Simple edge agent endpoints (registration_token-based, no API key) ──────
class BootstrapRegisterBody(BaseModel):
    registration_token: str  # one-time token generated by the dashboard
    cameras: list[str]


@edge_router.post("/register/bootstrap")
async def bootstrap_register_cameras(
    body: BootstrapRegisterBody,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """
    Bootstrap registration for the downloadable Python Edge Agent.

    Requires a one-time ``registration_token`` obtained from the dashboard
    (generated by the onboarding step 5 or the Install Edge Agent page).
    The token is consumed on first use and expires after 15 minutes.
    """
    tenant_id = _consume_bootstrap_token(body.registration_token)
    if not tenant_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired registration_token. Generate a new one from the dashboard.",
        )

    tenant_res = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    if not tenant_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Tenant not found")

    created = 0
    for ip in body.cameras:
        cam_id = f"cam-{ip.replace('.', '-')}"
        existing = await session.execute(
            select(CameraConfig).where(
                CameraConfig.tenant_id == tenant_id,
                CameraConfig.camera_id == cam_id,
            )
        )
        if existing.scalar_one_or_none():
            continue
        cam = CameraConfig(
            tenant_id=tenant_id,
            camera_id=cam_id,
            name=f"Camera {ip}",
            location="Auto-detected",
            fps_target=10,
            enabled=True,
        )
        cam.set_rtsp_url(f"rtsp://{ip}:554/stream1")
        session.add(cam)
        created += 1

    # Provision (or reuse) an EdgeAgent credential so the downloaded agent has
    # something to authenticate every heartbeat/event call with (X-API-Key).
    existing_agent = (
        await session.execute(
            select(EdgeAgent).where(EdgeAgent.tenant_id == tenant_id)
        )
    ).scalars().first()
    if existing_agent is not None:
        agent = existing_agent
    else:
        from ..services.tenant_service import provision_edge_agent

        agent = await provision_edge_agent(
            session,
            tenant_id,
            device_type="windows",
            device_name="Edge Agent (bootstrap)",
        )
    await session.commit()
    return {
        "registered": created,
        "total": len(body.cameras),
        "agent_id": agent.id,
        "api_key": agent.api_key,
        "store_id": "auto-detected",
    }


# ─── Downloadable, runnable Edge Agent package ──────────────────────────────
agent_download_router = APIRouter(prefix="/api/agent", tags=["edge-agent"])

# Repo root → vantag/  (edge_router.py is at vantag/backend/api/edge_router.py)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_AGENT_PKG_DIR = _REPO_ROOT / "windows_agent"

_RUN_BAT = """@echo off
REM Vantag Edge Agent launcher (Windows)
cd /d "%~dp0"
if not exist "requirements.txt" (
  echo.
  echo ============================================================
  echo   STOP - the files are still inside the ZIP.
  echo.
  echo   You double-clicked run.bat from inside the zip preview.
  echo   Please do this instead:
  echo     1^) Close this window
  echo     2^) Find vantag-edge-agent-windows.zip in your Downloads
  echo     3^) Right-click it and choose "Extract All..."
  echo     4^) Open the EXTRACTED folder
  echo     5^) Double-click run.bat there
  echo ============================================================
  echo.
  pause
  exit /b 1
)
where python >nul 2>nul || (echo Python 3.10+ is required. Install from python.org && pause && exit /b 1)
if not exist .venv (python -m venv .venv)
call .venv\\Scripts\\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m agent.main
pause
"""

_RUN_SH = """#!/usr/bin/env bash
# Vantag Edge Agent launcher (Linux/macOS)
set -e
cd "$(dirname "$0")"
if [ ! -f requirements.txt ]; then
  echo "ERROR: requirements.txt not found. Did you extract the zip first?"
  echo "Run:  unzip vantag-edge-agent-linux.zip -d vantag-agent && cd vantag-agent && ./run.sh"
  exit 1
fi
command -v python3 >/dev/null 2>&1 || { echo "Python 3.10+ is required."; exit 1; }
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m agent.main
"""

_README = """# Vantag Edge Agent - SETUP INSTRUCTIONS

############################################################
#  STEP 1 (IMPORTANT): EXTRACT THIS ZIP FIRST              #
#  Do NOT run run.bat from inside the zip preview window.  #
#  Right-click the downloaded .zip -> "Extract All..."     #
#  then open the extracted folder before continuing.       #
############################################################

This package is pre-configured for YOUR account (your keys are already inside
config.json - keep it private).

## What this does
It runs on a PC that is on the SAME local network (LAN) as your cameras. It
connects OUT to the Vantag cloud, so your cameras never need to be exposed to
the internet. This is why cameras on your LAN cannot be tested directly from
the website - the Edge Agent is what reaches them.

## Requirements
- A Windows or Linux PC kept switched on, on the same network as the cameras
- Python 3.10 or newer (Windows: install from https://python.org and tick
  "Add Python to PATH" during install)

## Windows - how to run
1. Extract the zip (see STEP 1 above).
2. Open the extracted folder.
3. Double-click `run.bat`.
   The first run downloads dependencies (a few minutes) and then starts.
4. Leave the window open. Your cameras turn ONLINE in the dashboard in ~30s.

## Linux / Raspberry Pi - how to run
    unzip vantag-edge-agent-linux.zip -d vantag-agent
    cd vantag-agent
    chmod +x run.sh
    ./run.sh

## After it starts
- Cameras appear ONLINE in your dashboard within ~30 seconds.
- Use "Auto-Scan with Edge Agent" on the Manage Cameras page to discover
  cameras on your LAN automatically.
- Real AI detections show on the Incidents page with snapshot evidence.

## Need help?
Email support@retailnazar.com (India) / support@retail-vantag.com, or use the
"Need help setting up?" chat in the app.
"""


def _agent_version() -> str:
    """Read __version__ from the bundled agent package (single source of truth)."""
    try:
        import re
        text = (_AGENT_PKG_DIR / "agent" / "__init__.py").read_text(encoding="utf-8")
        m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return "0.0.0"


def _build_agent_zip(config: dict, platform: str) -> bytes:
    import io
    import json
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Bundle the agent python package (windows_agent/agent/*.py).
        pkg = _AGENT_PKG_DIR / "agent"
        if pkg.exists():
            for path in pkg.rglob("*.py"):
                arc = Path("agent") / path.relative_to(pkg)
                zf.write(path, str(arc))
        # requirements.txt (from the agent dir, fall back to a minimal set).
        req = _AGENT_PKG_DIR / "requirements.txt"
        if req.exists():
            zf.write(req, "requirements.txt")
        else:
            zf.writestr(
                "requirements.txt",
                "opencv-python-headless\nonnxruntime\nnumpy\nrequests\npaho-mqtt\npsutil\n",
            )
        # Prefilled config.json (sits next to the package; loaded by config.load()).
        zf.writestr("config.json", json.dumps(config, indent=2))
        # MediaPipe 21-point hand-landmark model for the High-Value Counter
        # handover detector (agent/hand_landmarks.py resolves it relative to
        # the agent package). Bundled so the agent needs no runtime download.
        hand_task = _REPO_ROOT / "models" / "hand_landmarker.task"
        if hand_task.exists():
            zf.write(hand_task, "models/hand_landmarker.task")
        # Version stamp so users can tell which build they have.
        zf.writestr("VERSION.txt", f"Vantag Edge Agent v{_agent_version()}\n")
        # Launchers + readme.
        zf.writestr("run.bat", _RUN_BAT)
        zf.writestr("run.sh", _RUN_SH)
        zf.writestr("README.md", _README)
    return buf.getvalue()


@agent_download_router.get("/version")
async def agent_version_info():
    """Public (no-auth) endpoint so the Download page can display the
    current Edge Agent version before the user clicks download."""
    return {"version": _agent_version()}


@agent_download_router.get("/download")
async def download_agent(
    request: Request,
    platform: str = "windows",
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Build and return a credentialed, ready-to-run Edge Agent zip."""
    from fastapi import Response

    tenant_id = user["tenant_id"]

    # Provision (or reuse) the caller's EdgeAgent credential.
    agent = (
        await session.execute(
            select(EdgeAgent).where(EdgeAgent.tenant_id == tenant_id)
        )
    ).scalars().first()
    if agent is None:
        from ..services.tenant_service import provision_edge_agent

        agent = await provision_edge_agent(
            session,
            tenant_id,
            device_type=platform,
            device_name="Edge Agent (download)",
        )
        await session.commit()

    # Load this tenant's cameras to prefill the agent config.
    cams = (
        await session.execute(
            select(CameraConfig).where(
                CameraConfig.tenant_id == tenant_id,
                CameraConfig.enabled == True,  # noqa: E712
            )
        )
    ).scalars().all()

    # Behind an nginx reverse-proxy, request.base_url resolves to the internal
    # address (http://127.0.0.1:8000).  Use the forwarded headers that nginx
    # sends (X-Forwarded-Proto + Host) to build the correct public URL so the
    # downloaded config.json points the store-LAN agent at the real domain.
    proto = request.headers.get("X-Forwarded-Proto", "https")
    host = request.headers.get("Host", request.url.netloc)
    # Nginx 301-redirects "www.<domain>" -> "<domain>" for canonicalization.
    # HTTP clients downgrade POST->GET on a 301, so if the agent's baked-in
    # backend_url uses the "www." host, every heartbeat/frame-push POST the
    # agent sends gets silently turned into a GET and never reaches the
    # backend. Always strip "www." here so the agent talks to the bare
    # canonical domain directly and never hits that redirect.
    if host.startswith("www."):
        host = host[4:]
    backend_url = f"{proto}://{host}"
    # MQTT broker is on the same VPS — strip the port from the Host header to
    # get just the hostname (retail-vantag.com / retailnazar.com / etc.)
    mqtt_host = host.split(":")[0]

    config = {
        "api_key": agent.api_key,
        "agent_id": agent.id,
        "backend_url": backend_url,
        "mqtt_host": mqtt_host,
        "mqtt_port": int(os.getenv("MQTT_PORT", "1883")),
        # Broker credentials so the agent can authenticate (allow_anonymous
        # is disabled). Env-overridable for rotation.
        "mqtt_username": os.getenv("MQTT_EDGE_USERNAME", "vantag_edge"),
        "mqtt_password": os.getenv("MQTT_EDGE_PASSWORD", "nKZapdpNOpBnNrS8DMTDp_7IRa32IcDO"),
        "tenant_id": tenant_id,
        # NOTE: keys here MUST match windows_agent/agent/config.py::CameraConfig
        # fields (id, name, rtsp_url, location, ...). Any extra/renamed key makes
        # CameraConfig(**c) raise TypeError, which AgentConfig.load() swallows and
        # then falls back to an EMPTY config (no api_key) -> dead agent.
        "cameras": [
            {
                "id": c.camera_id,
                "name": c.name,
                "rtsp_url": (c.get_rtsp_url() if hasattr(c, "get_rtsp_url") else None) or "",
                "location": getattr(c, "location", "") or "",
                "confidence": (getattr(c, "analyzer_config", None) or {}).get("confidence_threshold"),
            }
            for c in cams
        ],
    }

    data = _build_agent_zip(config, platform)
    fname = f"vantag-edge-agent-{platform}-v{_agent_version()}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
