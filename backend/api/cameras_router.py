"""
backend/api/cameras_router.py
==============================
Camera management REST API for the Vantag platform.

Endpoints
---------
GET  /api/cameras                           â€“ list all cameras with health status
GET  /api/cameras/{camera_id}               â€“ camera detail + config
GET  /api/cameras/{camera_id}/snapshot      â€“ latest frame as JPEG
POST /api/cameras/{camera_id}/zones         â€“ update zone polygon config
GET  /api/cameras/{camera_id}/stream        â€“ MJPEG streaming (multipart/x-mixed-replace)
POST /api/cameras/scan                      â€“ auto-scan LAN for RTSP cameras
POST /api/cameras/test                      â€“ test RTSP connection and return thumbnail
POST /api/cameras                           â€“ add a new camera (persist to YAML)
DELETE /api/cameras/{camera_id}             â€“ remove a camera (persist to YAML)
"""

from __future__ import annotations

import asyncio
import base64
import io
import ipaddress
import logging
import socket
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CameraResponse, CameraStatus, ZonePolygon, ZoneUpdateRequest, SensitivityUpdateRequest
from ..middleware.tenant_middleware import get_current_user_id
from ..db.database import get_session
from ..db.models.camera import CameraConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cameras", tags=["Cameras"])

# ---------------------------------------------------------------------------
# Pipeline reference (injected at startup)
# ---------------------------------------------------------------------------

_pipeline = None  # type: ignore[assignment]


def set_pipeline(pipeline: object) -> None:  # noqa: ANN001
    """Inject the ``VantagePipeline`` singleton into this router."""
    global _pipeline  # noqa: PLW0603
    _pipeline = pipeline


def _get_pipeline():  # noqa: ANN202
    if _pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Inference pipeline is not yet initialised.",
        )
    return _pipeline


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_camera_response(cam, health_entry: Optional[dict]) -> CameraResponse:
    """Convert a ``CameraConfig`` + health entry into a ``CameraResponse``."""
    if health_entry is None:
        cam_status = CameraStatus.OFFLINE
        consecutive_failures = 0
        last_checked_at = None
    elif health_entry.get("healthy", False):
        cam_status = CameraStatus.ONLINE
        consecutive_failures = 0
        last_checked_at = _parse_ts(health_entry.get("last_checked"))
    else:
        failures = health_entry.get("consecutive_failures", 0)
        cam_status = CameraStatus.DEGRADED if failures < 5 else CameraStatus.OFFLINE
        consecutive_failures = failures
        last_checked_at = _parse_ts(health_entry.get("last_checked"))

    zones = [
        ZonePolygon(name=z.name, points=z.points)
        for z in cam.zones
    ]

    # Derive a store_id from the location field (same logic as stores_router).
    prefix = cam.location.split("â€“")[0].strip()
    store_id = prefix.lower().replace(" ", "_")

    return CameraResponse(
        camera_id=cam.id,
        name=cam.name,
        location=cam.location,
        store_id=store_id,
        rtsp_url=_mask_rtsp(cam.rtsp_url),
        resolution_width=cam.resolution.width,
        resolution_height=cam.resolution.height,
        fps_target=cam.fps_target,
        enabled=cam.enabled,
        low_light_mode=cam.low_light_mode,
        status=cam_status,
        consecutive_failures=consecutive_failures,
        last_checked_at=last_checked_at,
        zones=zones,
    )


def _mask_rtsp(url: str) -> str:
    """Replace credentials in RTSP URL with asterisks for security."""
    import re
    return re.sub(r"(rtsp://)([^@]+)@", r"\1***@", url)


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    """Safely parse an ISO-8601 timestamp string, returning None on failure."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _encode_jpeg(frame: np.ndarray, quality: int = 85) -> bytes:
    """Encode a BGR numpy frame to JPEG bytes."""
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("Failed to encode frame as JPEG.")
    return buf.tobytes()


# ---------------------------------------------------------------------------
# GET /api/cameras
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=List[CameraResponse],
    summary="List all cameras with health status",
)
async def list_cameras(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> List[CameraResponse]:
    """Return all cameras registered for the current tenant (DB-backed).

    This is the single source of truth shared with the edge agent. Cameras the
    user adds manually or that the edge agent auto-discovers both land in the
    tenant-scoped ``CameraConfig`` table, so the dashboard and the agent always
    agree on the camera list.
    """
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        return []

    try:
        rows = (
            await session.execute(
                select(CameraConfig)
                .where(CameraConfig.tenant_id == tenant_id)
                .order_by(CameraConfig.created_at)
            )
        ).scalars().all()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load cameras from DB | tenant=%s err=%s", tenant_id, exc)
        return []

    return [_db_camera_to_response(row) for row in rows]


def _db_camera_to_response(row) -> CameraResponse:  # noqa: ANN001
    """Convert a ``CameraConfig`` DB row into the API ``CameraResponse``."""
    conn = (getattr(row, "conn_status", "") or "").lower()
    if conn == "online":
        cam_status = CameraStatus.ONLINE
    else:
        # pending / offline / unknown -> offline until the agent confirms a frame
        cam_status = CameraStatus.OFFLINE

    location = row.location or ""
    prefix = location.split("\u2013")[0].split("-")[0].strip() if location else ""
    store_id = (prefix or "auto-detected").lower().replace(" ", "_")

    try:
        rtsp = row.get_rtsp_url() if hasattr(row, "get_rtsp_url") else None
    except Exception:  # noqa: BLE001
        rtsp = None

    try:
        _cfg = dict(getattr(row, "analyzer_config", None) or {})
        _conf = float(_cfg.get("confidence_threshold", 0.5))
    except (TypeError, ValueError):
        _conf = 0.5
    _conf = max(0.1, min(0.95, _conf))

    return CameraResponse(
        camera_id=row.camera_id,
        name=row.name or row.camera_id,
        location=location,
        store_id=store_id,
        rtsp_url=_mask_rtsp(rtsp) if rtsp else "",
        resolution_width=getattr(row, "resolution_width", None) or 1920,
        resolution_height=getattr(row, "resolution_height", None) or 1080,
        fps_target=getattr(row, "fps_target", None) or 15,
        enabled=bool(getattr(row, "enabled", False)),
        low_light_mode=bool(getattr(row, "low_light_mode", False)),
        status=cam_status,
        consecutive_failures=0,
        last_checked_at=getattr(row, "last_connected_at", None),
        zones=[],
        confidence_threshold=_conf,
    )


# ---------------------------------------------------------------------------
# GET /api/cameras/discovered  (edge-mode auto-detected list)
# NOTE: must be declared BEFORE the dynamic "/{camera_id}" route below,
# otherwise FastAPI matches "/discovered" against "/{camera_id}".
# ---------------------------------------------------------------------------


class DiscoveredCamera(BaseModel):
    camera_id: str
    name: str
    ip: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    conn_status: str = "pending"
    port: Optional[int] = None
    rtsp_path: Optional[str] = None
    thumbnail_url: Optional[str] = None
    needs_credentials: bool = False
    confidence: Optional[float] = None


@router.get(
    "/discovered",
    response_model=List[DiscoveredCamera],
    summary="List edge-agent auto-detected cameras awaiting confirmation",
)
async def list_discovered_cameras(
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> List[DiscoveredCamera]:
    """Return cameras the tenant's edge agent found on the store LAN that have
    not yet been confirmed (``enabled=False``)."""
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")

    rows = (
        await session.execute(
            select(CameraConfig).where(
                CameraConfig.tenant_id == tenant_id,
                CameraConfig.enabled == False,  # noqa: E712
                CameraConfig.camera_id.like("disc-%"),
            )
        )
    ).scalars().all()

    out: List[DiscoveredCamera] = []
    for row in rows:
        probe = row.probe_result or {}
        out.append(
            DiscoveredCamera(
                camera_id=row.camera_id,
                name=row.name or (row.brand or f"Camera {row.ip_address}"),
                ip=row.ip_address,
                brand=row.brand,
                model=row.model,
                conn_status=row.conn_status or "pending",
                port=probe.get("port"),
                rtsp_path=probe.get("rtsp_path"),
                thumbnail_url=probe.get("thumbnail_url"),
                needs_credentials=bool(probe.get("needs_credentials")),
                confidence=probe.get("confidence"),
            )
        )
    return out


# ---------------------------------------------------------------------------
# GET /api/cameras/{camera_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{camera_id}",
    response_model=CameraResponse,
    summary="Get camera detail and configuration",
)
async def get_camera(
    camera_id: str,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> CameraResponse:
    """Return full configuration and current health state for a single camera."""
    row = await _get_db_camera(session, user.get("tenant_id"), camera_id)
    return _db_camera_to_response(row)


async def _get_db_camera(session: AsyncSession, tenant_id, camera_id: str):  # noqa: ANN001
    """Fetch a tenant-scoped camera row or raise 404."""
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found.")
    row = (
        await session.execute(
            select(CameraConfig).where(
                CameraConfig.tenant_id == tenant_id,
                CameraConfig.camera_id == camera_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )
    return row


# ---------------------------------------------------------------------------
# GET /api/cameras/{camera_id}/snapshot
# ---------------------------------------------------------------------------


@router.get(
    "/{camera_id}/snapshot",
    summary="Get latest frame as JPEG",
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def get_snapshot(
    camera_id: str,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """
    Return the most recent captured frame for a camera as a JPEG image.

    Responds with ``404`` if the camera does not exist and ``503`` if no
    frame is currently available (stream is offline or buffer is empty).
    """
    # Verify camera exists for this tenant.
    await _get_db_camera(session, user.get("tenant_id"), camera_id)

    # Live frames are only available when an on-box inference pipeline is
    # running. For SaaS/edge deployments the camera streams on the agent, so
    # there is no local frame -> report 503 (the UI shows an "offline" tile).
    if _pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No frame available for camera '{camera_id}'. Stream may be offline.",
        )
    pipeline = _pipeline

    # Prefer a cached annotated snapshot over a raw frame.
    cached: Optional[bytes] = pipeline.latest_snapshots.get(camera_id)
    if cached:
        return Response(content=cached, media_type="image/jpeg")

    # Fall back to raw frame from the stream manager.
    frame = pipeline.stream_manager.get_frame(camera_id)
    if frame is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No frame available for camera '{camera_id}'. Stream may be offline.",
        )

    try:
        jpeg_bytes = _encode_jpeg(frame)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Frame encoding failed: {exc}",
        ) from exc

    return Response(content=jpeg_bytes, media_type="image/jpeg")


# ---------------------------------------------------------------------------
# POST /api/cameras/{camera_id}/zones
# ---------------------------------------------------------------------------


@router.post(
    "/{camera_id}/zones",
    response_model=CameraResponse,
    summary="Update zone polygon configuration",
)
async def update_zones(
    camera_id: str,
    body: ZoneUpdateRequest,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> CameraResponse:
    """
    Replace the zone polygon configuration for a camera.

    Persisted to the camera's ``analyzer_config`` JSON in the tenant DB so the
    edge agent receives the zones on its next config sync. If an on-box
    pipeline is running, the change is also applied in-memory immediately.
    """
    row = await _get_db_camera(session, user.get("tenant_id"), camera_id)

    zones_payload = [{"name": z.name, "points": z.points} for z in body.zones]
    try:
        cfg = dict(getattr(row, "analyzer_config", None) or {})
        cfg["zones"] = zones_payload
        row.analyzer_config = cfg
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save zones: {exc}",
        ) from exc

    # Best-effort in-memory apply for on-box deployments.
    if _pipeline is not None:
        try:
            from ..ingestion.camera_registry import ZoneConfig
            cam = _pipeline.registry.get_camera(camera_id)
            cam.zones = [ZoneConfig(name=z.name, points=z.points) for z in body.zones]
        except Exception:  # noqa: BLE001
            pass

    logger.info("Zone config updated | camera_id=%s zones=%d", camera_id, len(zones_payload))
    resp = _db_camera_to_response(row)
    resp.zones = [ZonePolygon(name=z["name"], points=z["points"]) for z in zones_payload]
    return resp


# ---------------------------------------------------------------------------
# PATCH /api/cameras/{camera_id}/sensitivity
# ---------------------------------------------------------------------------


@router.patch(
    "/{camera_id}/sensitivity",
    response_model=CameraResponse,
    summary="Update detection sensitivity (confidence threshold)",
)
async def update_sensitivity(
    camera_id: str,
    body: SensitivityUpdateRequest,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> CameraResponse:
    """
    Set the per-camera detection confidence threshold.

    Persisted to the camera's ``analyzer_config`` JSON so the Edge Agent
    receives it on its next config sync (~5 s) and restarts that camera's
    worker with the new threshold. Lower threshold = more sensitive (more
    detections/alerts); higher = fewer false alarms.
    """
    row = await _get_db_camera(session, user.get("tenant_id"), camera_id)

    try:
        cfg = dict(getattr(row, "analyzer_config", None) or {})
        cfg["confidence_threshold"] = round(float(body.confidence_threshold), 3)
        row.analyzer_config = cfg
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save sensitivity: {exc}",
        ) from exc

    # Best-effort in-memory apply for on-box deployments.
    if _pipeline is not None:
        try:
            cam = _pipeline.registry.get_camera(camera_id)
            cam.analyzer_config = dict(getattr(cam, "analyzer_config", None) or {})
            cam.analyzer_config["confidence_threshold"] = cfg["confidence_threshold"]
        except Exception:  # noqa: BLE001
            pass

    logger.info(
        "Sensitivity updated | camera_id=%s confidence=%.3f",
        camera_id, cfg["confidence_threshold"],
    )
    return _db_camera_to_response(row)


# ---------------------------------------------------------------------------
# GET /api/cameras/{camera_id}/stream  (MJPEG)
# ---------------------------------------------------------------------------


@router.get(
    "/{camera_id}/stream",
    summary="MJPEG live stream",
    responses={200: {"content": {"multipart/x-mixed-replace; boundary=frame": {}}}},
)
async def mjpeg_stream(camera_id: str, request: Request, user: dict = Depends(get_current_user_id)) -> StreamingResponse:
    """
    Stream live MJPEG video from a camera.

    Uses ``multipart/x-mixed-replace`` so compatible browsers can display
    the stream directly.  Frames are pulled from the ``StreamManager`` at
    the camera's configured FPS target (capped at 30 fps for API stability).

    The stream ends when the client disconnects.
    """
    pipeline = _get_pipeline()
    try:
        cam = pipeline.registry.get_camera(camera_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    fps = min(cam.fps_target, 30)
    frame_interval = 1.0 / fps

    async def generate() -> AsyncGenerator[bytes, None]:
        while not await request.is_disconnected():
            # Prefer annotated snapshot, fall back to raw frame.
            jpeg_bytes: Optional[bytes] = pipeline.latest_snapshots.get(camera_id)
            if jpeg_bytes is None:
                frame = pipeline.stream_manager.get_frame(camera_id)
                if frame is not None:
                    try:
                        jpeg_bytes = _encode_jpeg(frame)
                    except Exception:  # noqa: BLE001
                        pass

            if jpeg_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg_bytes
                    + b"\r\n"
                )
            else:
                # Send a placeholder black frame when no data is available.
                placeholder = np.zeros((240, 320, 3), dtype=np.uint8)
                cv2.putText(
                    placeholder,
                    "No Signal",
                    (80, 130),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (255, 255, 255),
                    2,
                )
                try:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + _encode_jpeg(placeholder)
                        + b"\r\n"
                    )
                except Exception:  # noqa: BLE001
                    pass

            await asyncio.sleep(frame_interval)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ---------------------------------------------------------------------------
# POST /api/cameras/scan
# ---------------------------------------------------------------------------

_SCAN_SEMAPHORE_SIZE = 50
_PROBE_TIMEOUT = 0.5  # seconds per IP probe
_RTSP_PORT = 554

# Common vendor hint patterns by IP last-octet bands (rough heuristics)
_VENDOR_HINTS = {
    "Dahua": ["admin", "dahua"],
    "Hikvision": ["admin", "hikvision"],
}


class ScanRequest(BaseModel):
    subnet: Optional[str] = None  # e.g. "192.168.1.0/24"


class DiscoveredCamera(BaseModel):
    ip: str
    port: int
    vendor_hint: Optional[str] = None


@router.post(
    "/scan",
    response_model=List[DiscoveredCamera],
    summary="Scan LAN for RTSP cameras (port 554)",
)
async def scan_cameras(
    body: ScanRequest,
    user: dict = Depends(get_current_user_id),
) -> List[DiscoveredCamera]:
    """
    Probe every host in a /24 subnet on port 554 (RTSP) using asyncio
    socket connects with a 0.5 s timeout per host.  Runs up to 50 probes
    in parallel.  If no subnet is provided the server's primary interface
    subnet is auto-detected.

    Returns a list of hosts that accepted the TCP connection.
    """
    # ---- Determine subnet ----
    if body.subnet:
        try:
            network = ipaddress.IPv4Network(body.subnet, strict=False)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid subnet: {exc}") from exc
    else:
        # Auto-detect server's primary LAN subnet
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:  # noqa: BLE001
            local_ip = "192.168.1.1"
        network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)

    hosts = list(network.hosts())

    semaphore = asyncio.Semaphore(_SCAN_SEMAPHORE_SIZE)
    results: List[DiscoveredCamera] = []
    lock = asyncio.Lock()

    async def probe_host(ip: str) -> None:
        async with semaphore:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, _RTSP_PORT),
                    timeout=_PROBE_TIMEOUT,
                )
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:  # noqa: BLE001
                    pass

                # Guess vendor from OUI or patterns â€” lightweight heuristic
                vendor: Optional[str] = None
                last_octet = int(ip.split(".")[-1])
                # Simple range heuristic; real production would do OUI lookup
                if 100 <= last_octet <= 150:
                    vendor = "Dahua"
                elif 200 <= last_octet <= 254:
                    vendor = "Hikvision"

                async with lock:
                    results.append(DiscoveredCamera(ip=ip, port=_RTSP_PORT, vendor_hint=vendor))
            except (asyncio.TimeoutError, ConnectionRefusedError, OSError):
                pass

    await asyncio.gather(*[probe_host(str(h)) for h in hosts])
    logger.info("Network scan complete | subnet=%s found=%d", network, len(results))
    return results


# ---------------------------------------------------------------------------
# POST /api/cameras/test
# ---------------------------------------------------------------------------

class TestConnectionRequest(BaseModel):
    ip: str
    port: int = 554
    username: Optional[str] = None
    password: Optional[str] = None
    rtsp_path: str = "/"


class TestConnectionResponse(BaseModel):
    success: bool
    thumbnail_base64: Optional[str] = None
    error: Optional[str] = None
    # True when the test could not run because the camera is on a private LAN
    # the cloud cannot reach. The Edge Agent validates these locally, so the UI
    # should still allow the camera to be saved.
    lan_unreachable: bool = False


@router.post(
    "/test",
    response_model=TestConnectionResponse,
    summary="Test RTSP connection and capture a thumbnail",
)
async def test_camera_connection(
    body: TestConnectionRequest,
    user: dict = Depends(get_current_user_id),
) -> TestConnectionResponse:
    """
    Open an RTSP stream using OpenCV (via FFMPEG back-end), read one frame
    within 5 seconds, and return a JPEG thumbnail as base64.
    """
    # Build RTSP URL
    path = body.rtsp_path if body.rtsp_path.startswith("/") else f"/{body.rtsp_path}"
    if body.username and body.password:
        rtsp_url = f"rtsp://{body.username}:{body.password}@{body.ip}:{body.port}{path}"
    else:
        rtsp_url = f"rtsp://{body.ip}:{body.port}{path}"

    # The backend runs in the cloud and cannot route to a private LAN address
    # (e.g. 192.168.x.x / 10.x / 172.16-31.x). A camera on the user's local
    # network must be reached by the Edge Agent, not from the cloud. Detect
    # this and return an actionable message instead of a confusing timeout.
    try:
        import ipaddress
        ip_obj = ipaddress.ip_address(body.ip)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
            return TestConnectionResponse(
                success=False,
                lan_unreachable=True,
                error=(
                    "This camera is on your local network ("
                    f"{body.ip}), which our cloud cannot reach directly. "
                    "That's expected — just click \"Save Camera\" and your "
                    "on-site Edge Agent will connect to it locally and start "
                    "monitoring. (No cloud test is needed for LAN cameras.)"
                ),
            )
    except ValueError:
        # Not a literal IP (could be a hostname/DDNS) - allow the probe to run.
        pass

    def _capture() -> TestConnectionResponse:
        cap = None
        try:
            cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)
            cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)

            if not cap.isOpened():
                return TestConnectionResponse(success=False, error="Failed to open RTSP stream.")

            ok, frame = cap.read()
            if not ok or frame is None:
                return TestConnectionResponse(success=False, error="Stream opened but could not read a frame.")

            # Encode frame as JPEG and base64
            ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ok2:
                return TestConnectionResponse(success=True)

            thumbnail_b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
            return TestConnectionResponse(success=True, thumbnail_base64=thumbnail_b64)
        except Exception as exc:  # noqa: BLE001
            return TestConnectionResponse(success=False, error=str(exc))
        finally:
            if cap is not None:
                cap.release()

    # Run blocking cv2 call in a thread pool
    result = await asyncio.wait_for(
        asyncio.to_thread(_capture),
        timeout=10.0,
    )
    return result


# ---------------------------------------------------------------------------
# POST /api/cameras  (Create)
# ---------------------------------------------------------------------------

class CreateCameraRequest(BaseModel):
    name: str
    location: str
    ip: str
    port: int = 554
    username: Optional[str] = None
    password: Optional[str] = None
    rtsp_path: str = "/"
    resolution: str = "1920x1080"   # "WxH"
    fps: int = 15
    enabled: bool = True
    low_light_mode: bool = False


@router.post(
    "",
    response_model=CameraResponse,
    status_code=201,
    summary="Add a new camera",
)
async def create_camera(
    body: CreateCameraRequest,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> CameraResponse:
    """
    Register a new camera in the tenant's database so the store's edge agent
    picks it up on its next config sync, and return the saved config.
    """
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")

    # Build RTSP URL
    path = body.rtsp_path if body.rtsp_path.startswith("/") else f"/{body.rtsp_path}"
    if body.username and body.password:
        rtsp_url = f"rtsp://{body.username}:{body.password}@{body.ip}:{body.port}{path}"
    else:
        rtsp_url = f"rtsp://{body.ip}:{body.port}{path}"

    # Parse resolution
    try:
        w_str, h_str = body.resolution.split("x")
        width, height = int(w_str), int(h_str)
    except (ValueError, AttributeError):
        width, height = 1920, 1080

    # Generate a unique camera ID
    cam_id = f"cam-{uuid.uuid4().hex[:8]}"

    row = CameraConfig(
        tenant_id=tenant_id,
        camera_id=cam_id,
        name=body.name,
        ip_address=body.ip,
        location=body.location,
        resolution_width=width,
        resolution_height=height,
        fps_target=body.fps,
        enabled=body.enabled,
        low_light_mode=body.low_light_mode,
        conn_status="pending",
    )
    row.set_rtsp_url(rtsp_url)

    try:
        session.add(row)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to register camera: {exc}") from exc

    logger.info(
        "Camera created via API | camera_id=%s name=%s tenant=%s",
        cam_id, body.name, tenant_id,
    )

    store_id = (body.location or "auto-detected").split("–")[0].strip().lower().replace(" ", "_")
    return CameraResponse(
        camera_id=cam_id,
        name=body.name,
        location=body.location,
        store_id=store_id,
        rtsp_url=_mask_rtsp(rtsp_url),
        resolution_width=width,
        resolution_height=height,
        fps_target=body.fps,
        enabled=body.enabled,
        low_light_mode=body.low_light_mode,
        status=CameraStatus.OFFLINE,
        consecutive_failures=0,
        last_checked_at=None,
        zones=[],
    )


# ---------------------------------------------------------------------------
# DELETE /api/cameras/{camera_id}
# ---------------------------------------------------------------------------

@router.delete(
    "/{camera_id}",
    status_code=204,
    summary="Delete a camera",
)
async def delete_camera(
    camera_id: str,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> None:
    """
    Remove a camera from the tenant's database so the edge agent stops
    monitoring it on its next config sync.
    """
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")

    row = (
        await session.execute(
            select(CameraConfig).where(
                CameraConfig.tenant_id == tenant_id,
                CameraConfig.camera_id == camera_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    try:
        await session.delete(row)
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove camera: {exc}",
        ) from exc

    logger.info("Camera deleted via API | camera_id=%s tenant=%s", camera_id, tenant_id)


# ---------------------------------------------------------------------------
# POST /api/cameras/auto-detect-path
# ---------------------------------------------------------------------------

# All known RTSP paths across all brands â€” tried concurrently
_BRAND_RTSP_PRESETS: dict = {
    "hikvision": {"port": 554, "paths": ["/Streaming/Channels/101", "/Streaming/Channels/102", "/h264/ch1/main/av_stream"]},
    "dahua":     {"port": 554, "paths": ["/cam/realmonitor?channel=1&subtype=0", "/cam/realmonitor?channel=1&subtype=1"]},
    "cpplus":    {"port": 554, "paths": ["/cam/realmonitor?channel=1&subtype=0"]},
    "tplink":    {"port": 554, "paths": ["/stream1", "/stream2"]},
    "reolink":   {"port": 554, "paths": ["/h264Preview_01_main", "/h264Preview_01_sub"]},
    "uniview":   {"port": 554, "paths": ["/media/video1", "/media/video2"]},
    "axis":      {"port": 554, "paths": ["/axis-media/media.amp"]},
    "bosch":     {"port": 554, "paths": ["/rtsp_tunnel"]},
    "ezviz":     {"port": 554, "paths": ["/Streaming/Channels/101"]},
    "xiaomi":    {"port": 554, "paths": ["/live/ch00_0"]},
    "onvif":     {"port": 554, "paths": ["/onvif/media_service", "/onvif1", "/onvif2"]},
    "generic":   {"port": 554, "paths": ["/stream", "/stream1", "/live", "/live.sdp", "/"]},
}

# Brand lookup by path prefix
_PATH_TO_BRAND: dict = {}
for _brand, _preset in _BRAND_RTSP_PRESETS.items():
    for _p in _preset["paths"]:
        _PATH_TO_BRAND[_p] = _brand.capitalize()


class AutoDetectPathRequest(BaseModel):
    ip: str
    port: int = 554
    username: Optional[str] = None
    password: Optional[str] = None


class AutoDetectPathResponse(BaseModel):
    success: bool
    port: Optional[int] = None
    path: Optional[str] = None
    brand_detected: Optional[str] = None
    thumbnail_base64: Optional[str] = None
    tried: Optional[int] = None
    message: Optional[str] = None


def _try_rtsp_path(ip: str, port: int, path: str, username: Optional[str], password: Optional[str]) -> Optional[dict]:
    """
    Blocking helper: open RTSP URL, read one frame within 3s.
    Returns dict with path/thumbnail on success, None on failure.
    """
    path = path if path.startswith("/") else f"/{path}"
    if username and password:
        rtsp_url = f"rtsp://{username}:{password}@{ip}:{port}{path}"
    else:
        rtsp_url = f"rtsp://{ip}:{port}{path}"

    cap = None
    try:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000)
        if not cap.isOpened():
            return None
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        thumbnail = base64.b64encode(buf.tobytes()).decode("utf-8") if ok2 else None
        return {"path": path, "thumbnail": thumbnail}
    except Exception:  # noqa: BLE001
        return None
    finally:
        if cap is not None:
            cap.release()


@router.post(
    "/auto-detect-path",
    response_model=AutoDetectPathResponse,
    summary="AI-assisted RTSP path detection â€” tries all known brand paths concurrently",
)
async def auto_detect_rtsp_path(
    body: AutoDetectPathRequest,
    user: dict = Depends(get_current_user_id),
) -> AutoDetectPathResponse:
    """
    Concurrently probe all known RTSP paths for a camera IP.

    Strategy:
    1. Try ONVIF discovery first (graceful skip if ``onvif-zeep`` not installed).
    2. If ONVIF fails, run all candidate paths in ``asyncio.wait(..., FIRST_COMPLETED)``.
       Each path is tried with a 3-second timeout.  Total cap: 30 seconds.
    3. Return the first URL that yields a valid video frame.
    """
    # 1. ONVIF attempt (best-effort)
    try:
        from onvif import ONVIFCamera  # type: ignore[import]
        def _onvif_probe() -> Optional[str]:
            try:
                cam_onvif = ONVIFCamera(body.ip, 80, body.username or "admin", body.password or "admin")
                media = cam_onvif.create_media_service()
                profiles = media.GetProfiles()
                if profiles:
                    uri_obj = media.GetStreamUri({
                        "StreamSetup": {"Stream": "RTP-Unicast", "Transport": {"Protocol": "RTSP"}},
                        "ProfileToken": profiles[0].token,
                    })
                    full_url: str = uri_obj.Uri
                    # Extract just the path
                    from urllib.parse import urlparse
                    parsed = urlparse(full_url)
                    return parsed.path or "/"
            except Exception:  # noqa: BLE001
                return None
            return None

        onvif_path = await asyncio.wait_for(asyncio.to_thread(_onvif_probe), timeout=5.0)
        if onvif_path:
            result = await asyncio.wait_for(
                asyncio.to_thread(_try_rtsp_path, body.ip, body.port, onvif_path, body.username, body.password),
                timeout=5.0,
            )
            if result:
                return AutoDetectPathResponse(
                    success=True,
                    port=body.port,
                    path=result["path"],
                    brand_detected="ONVIF",
                    thumbnail_base64=result.get("thumbnail"),
                )
    except (ImportError, asyncio.TimeoutError, Exception):  # noqa: BLE001
        pass  # ONVIF not available or failed â€” fall through to brute-force

    # 2. Concurrent brute-force across all known paths
    all_paths: List[str] = []
    seen: set = set()
    for preset in _BRAND_RTSP_PRESETS.values():
        for p in preset["paths"]:
            if p not in seen:
                all_paths.append(p)
                seen.add(p)

    total = len(all_paths)

    async def probe_path(path: str) -> Optional[dict]:
        result = await asyncio.to_thread(
            _try_rtsp_path, body.ip, body.port, path, body.username, body.password
        )
        if result:
            result["_path_key"] = path
        return result

    # Use wait(FIRST_COMPLETED) with 30s overall cap
    tasks = {asyncio.create_task(probe_path(p)): p for p in all_paths}
    pending = set(tasks.keys())
    deadline = asyncio.get_event_loop().time() + 30.0

    try:
        while pending:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            done, pending = await asyncio.wait(
                pending,
                timeout=min(remaining, 4.0),
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                result = task.result()
                if result:
                    # Cancel remaining tasks
                    for t in pending:
                        t.cancel()
                    path_key = result.get("_path_key", result["path"])
                    brand = _PATH_TO_BRAND.get(path_key, "Unknown").capitalize()
                    return AutoDetectPathResponse(
                        success=True,
                        port=body.port,
                        path=result["path"],
                        brand_detected=brand,
                        thumbnail_base64=result.get("thumbnail"),
                    )
    finally:
        # Clean up any remaining tasks
        for t in pending:
            t.cancel()

    return AutoDetectPathResponse(
        success=False,
        tried=total,
        message="Could not auto-detect. Contact support chat for help.",
    )


# ---------------------------------------------------------------------------
# POST /api/cameras/scan-request  (edge-mode auto-scan trigger)
# ---------------------------------------------------------------------------


@router.post(
    "/scan-request",
    summary="Ask the tenant's edge agent to run a LAN camera discovery scan",
)
async def request_camera_scan(user: dict = Depends(get_current_user_id)) -> dict:
    """Flag the tenant's edge agent to run an on-demand LAN camera scan.

    The agent picks up the flag on its next heartbeat (within a few seconds),
    scans its store network, and POSTs discovered cameras back to the backend,
    which surface in the dashboard's auto-detected list.
    """
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")
    from .edge_router import request_camera_scan as _flag_scan
    _flag_scan(tenant_id)
    return {"ok": True, "message": "Scan requested. Your edge agent will scan shortly."}


# ---------------------------------------------------------------------------
# POST /api/cameras/discovered/{camera_id}/confirm
# ---------------------------------------------------------------------------


class ConfirmDiscoveredRequest(BaseModel):
    name: Optional[str] = None
    location: str
    username: Optional[str] = None
    password: Optional[str] = None
    fps: int = 15
    resolution: str = "1920x1080"
    low_light_mode: bool = False


@router.post(
    "/discovered/{camera_id}/confirm",
    response_model=CameraResponse,
    summary="Confirm an auto-detected camera and add it to the live pipeline",
)
async def confirm_discovered_camera(
    camera_id: str,
    body: ConfirmDiscoveredRequest,
    user: dict = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
) -> CameraResponse:
    """Promote an edge-discovered camera to an active, monitored camera.

    Applies any credentials the user supplies, registers the camera in the live
    inference pipeline, and flips the DB row to ``enabled=True``.
    """
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant in session")

    row = (
        await session.execute(
            select(CameraConfig).where(
                CameraConfig.tenant_id == tenant_id,
                CameraConfig.camera_id == camera_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Discovered camera not found")

    probe = row.probe_result or {}
    port = probe.get("port") or 554
    path = probe.get("rtsp_path") or "/"
    if not path.startswith("/"):
        path = f"/{path}"

    # Build the final RTSP URL: prefer user credentials, else any stored URL.
    if body.username and body.password and row.ip_address:
        rtsp_url = f"rtsp://{body.username}:{body.password}@{row.ip_address}:{port}{path}"
    else:
        rtsp_url = row.get_rtsp_url() or (
            f"rtsp://{row.ip_address}:{port}{path}" if row.ip_address else None
        )
    if not rtsp_url:
        raise HTTPException(status_code=400, detail="No RTSP URL available for this camera")

    # Parse resolution
    try:
        w_str, h_str = body.resolution.split("x")
        width, height = int(w_str), int(h_str)
    except (ValueError, AttributeError):
        width, height = 1920, 1080

    cam_name = body.name or row.name or (row.brand or f"Camera {row.ip_address}")

    # Persist the confirmed camera to the tenant DB (single source of truth).
    # The edge agent picks this up on its next config sync. Status stays
    # "offline" until that agent heartbeats — the VPS cannot reach LAN cameras
    # directly, so it must not claim "online" here.
    row.enabled = True
    row.name = cam_name
    row.location = body.location
    row.resolution_width = width
    row.resolution_height = height
    row.fps_target = body.fps
    row.low_light_mode = body.low_light_mode
    row.set_rtsp_url(rtsp_url)
    try:
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to confirm camera: {exc}") from exc

    # Best-effort register in the live pipeline for on-box deployments only.
    if _pipeline is not None:
        try:
            from ..ingestion.camera_registry import (
                CameraConfig as RegCameraConfig,
                Resolution,
            )

            reg_id = f"cam-{uuid.uuid4().hex[:8]}"
            new_cam = RegCameraConfig(
                id=reg_id,
                name=cam_name,
                rtsp_url=rtsp_url,
                location=body.location,
                resolution=Resolution(width=width, height=height),
                fps_target=body.fps,
                enabled=True,
                low_light_mode=body.low_light_mode,
                zones=[],
                staff_zone_colors=[],
                analyzer_config={},
            )
            _pipeline.registry.add_camera(new_cam)
            row.conn_status = "online"
            await session.commit()
        except Exception:  # noqa: BLE001
            pass

    logger.info("Discovered camera confirmed | camera_id=%s name=%s", camera_id, cam_name)
    return _db_camera_to_response(row)


# ---------------------------------------------------------------------------
# Pipeline reference (injected at startup)
# ---------------------------------------------------------------------------

_pipeline = None  # type: ignore[assignment]


def set_pipeline(pipeline: object) -> None:  # noqa: ANN001
    """Inject the ``VantagePipeline`` singleton into this router."""
    global _pipeline  # noqa: PLW0603
    _pipeline = pipeline


def _get_pipeline():  # noqa: ANN202
    if _pipeline is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Inference pipeline is not yet initialised.",
        )
    return _pipeline

