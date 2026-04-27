"""
backend/api/cameras_router.py
==============================
Camera management REST API for the Vantag platform.

Endpoints
---------
GET  /api/cameras                           – list all cameras with health status
GET  /api/cameras/{camera_id}               – camera detail + config
GET  /api/cameras/{camera_id}/snapshot      – latest frame as JPEG
POST /api/cameras/{camera_id}/zones         – update zone polygon config
GET  /api/cameras/{camera_id}/stream        – MJPEG streaming (multipart/x-mixed-replace)
POST /api/cameras/scan                      – auto-scan LAN for RTSP cameras
POST /api/cameras/test                      – test RTSP connection and return thumbnail
POST /api/cameras                           – add a new camera (persist to YAML)
DELETE /api/cameras/{camera_id}             – remove a camera (persist to YAML)
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

from .models import CameraResponse, CameraStatus, ZonePolygon, ZoneUpdateRequest
from ..middleware.tenant_middleware import get_current_user_id

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
    prefix = cam.location.split("–")[0].strip()
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
async def list_cameras() -> List[CameraResponse]:
    """Return all cameras registered in the system along with their health state."""
    pipeline = _get_pipeline()
    try:
        cameras = pipeline.registry.all_cameras()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load camera registry: {exc}",
        ) from exc

    health_status: dict = {}
    if pipeline.health_monitor:
        health_status = pipeline.health_monitor.get_status()

    return [
        _build_camera_response(cam, health_status.get(cam.id))
        for cam in cameras
    ]


# ---------------------------------------------------------------------------
# GET /api/cameras/{camera_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{camera_id}",
    response_model=CameraResponse,
    summary="Get camera detail and configuration",
)
async def get_camera(camera_id: str) -> CameraResponse:
    """Return full configuration and current health state for a single camera."""
    pipeline = _get_pipeline()
    try:
        cam = pipeline.registry.get_camera(camera_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    health_status: dict = {}
    if pipeline.health_monitor:
        health_status = pipeline.health_monitor.get_status()

    return _build_camera_response(cam, health_status.get(camera_id))


# ---------------------------------------------------------------------------
# GET /api/cameras/{camera_id}/snapshot
# ---------------------------------------------------------------------------


@router.get(
    "/{camera_id}/snapshot",
    summary="Get latest frame as JPEG",
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def get_snapshot(camera_id: str) -> Response:
    """
    Return the most recent captured frame for a camera as a JPEG image.

    Responds with ``404`` if the camera does not exist and ``503`` if no
    frame is currently available (stream is offline or buffer is empty).
    """
    pipeline = _get_pipeline()

    # Verify camera exists.
    try:
        pipeline.registry.get_camera(camera_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

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
async def update_zones(camera_id: str, body: ZoneUpdateRequest) -> CameraResponse:
    """
    Replace the zone polygon configuration for a camera.

    The updated zones are applied in-memory immediately and will be used by
    all analyzers on the next processed frame.  To persist changes across
    restarts, update ``cameras.yaml`` separately.
    """
    pipeline = _get_pipeline()
    try:
        cam = pipeline.registry.get_camera(camera_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    from ..ingestion.camera_registry import ZoneConfig

    new_zones = [
        ZoneConfig(name=z.name, points=z.points)
        for z in body.zones
    ]
    cam.zones = new_zones
    logger.info(
        "Zone config updated | camera_id=%s zones=%d",
        camera_id,
        len(new_zones),
    )

    health_status: dict = {}
    if pipeline.health_monitor:
        health_status = pipeline.health_monitor.get_status()

    return _build_camera_response(cam, health_status.get(camera_id))


# ---------------------------------------------------------------------------
# GET /api/cameras/{camera_id}/stream  (MJPEG)
# ---------------------------------------------------------------------------


@router.get(
    "/{camera_id}/stream",
    summary="MJPEG live stream",
    responses={200: {"content": {"multipart/x-mixed-replace; boundary=frame": {}}}},
)
async def mjpeg_stream(camera_id: str, request: Request) -> StreamingResponse:
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

                # Guess vendor from OUI or patterns — lightweight heuristic
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
) -> CameraResponse:
    """
    Register a new camera, persist it to cameras.yaml, and return its config.
    """
    pipeline = _get_pipeline()

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

    from ..ingestion.camera_registry import CameraConfig, Resolution, ConfigError

    new_cam = CameraConfig(
        id=cam_id,
        name=body.name,
        rtsp_url=rtsp_url,
        location=body.location,
        resolution=Resolution(width=width, height=height),
        fps_target=body.fps,
        enabled=body.enabled,
        low_light_mode=body.low_light_mode,
        zones=[],
        staff_zone_colors=[],
        analyzer_config={},
    )

    try:
        pipeline.registry.add_camera(new_cam)
    except ConfigError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to register camera: {exc}") from exc

    logger.info("Camera created via API | camera_id=%s name=%s", cam_id, body.name)
    return _build_camera_response(new_cam, None)


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
) -> None:
    """
    Remove a camera from the registry and persist the change to cameras.yaml.
    """
    pipeline = _get_pipeline()

    try:
        pipeline.registry.remove_camera(camera_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove camera: {exc}",
        ) from exc

    logger.info("Camera deleted via API | camera_id=%s", camera_id)


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
    prefix = cam.location.split("–")[0].strip()
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
async def list_cameras() -> List[CameraResponse]:
    """Return all cameras registered in the system along with their health state."""
    pipeline = _get_pipeline()
    try:
        cameras = pipeline.registry.all_cameras()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load camera registry: {exc}",
        ) from exc

    health_status: dict = {}
    if pipeline.health_monitor:
        health_status = pipeline.health_monitor.get_status()

    return [
        _build_camera_response(cam, health_status.get(cam.id))
        for cam in cameras
    ]


# ---------------------------------------------------------------------------
# GET /api/cameras/{camera_id}
# ---------------------------------------------------------------------------


@router.get(
    "/{camera_id}",
    response_model=CameraResponse,
    summary="Get camera detail and configuration",
)
async def get_camera(camera_id: str) -> CameraResponse:
    """Return full configuration and current health state for a single camera."""
    pipeline = _get_pipeline()
    try:
        cam = pipeline.registry.get_camera(camera_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    health_status: dict = {}
    if pipeline.health_monitor:
        health_status = pipeline.health_monitor.get_status()

    return _build_camera_response(cam, health_status.get(camera_id))


# ---------------------------------------------------------------------------
# GET /api/cameras/{camera_id}/snapshot
# ---------------------------------------------------------------------------


@router.get(
    "/{camera_id}/snapshot",
    summary="Get latest frame as JPEG",
    responses={200: {"content": {"image/jpeg": {}}}},
)
async def get_snapshot(camera_id: str) -> Response:
    """
    Return the most recent captured frame for a camera as a JPEG image.

    Responds with ``404`` if the camera does not exist and ``503`` if no
    frame is currently available (stream is offline or buffer is empty).
    """
    pipeline = _get_pipeline()

    # Verify camera exists.
    try:
        pipeline.registry.get_camera(camera_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

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
async def update_zones(camera_id: str, body: ZoneUpdateRequest) -> CameraResponse:
    """
    Replace the zone polygon configuration for a camera.

    The updated zones are applied in-memory immediately and will be used by
    all analyzers on the next processed frame.  To persist changes across
    restarts, update ``cameras.yaml`` separately.
    """
    pipeline = _get_pipeline()
    try:
        cam = pipeline.registry.get_camera(camera_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera '{camera_id}' not found.",
        )

    from ..ingestion.camera_registry import ZoneConfig

    new_zones = [
        ZoneConfig(name=z.name, points=z.points)
        for z in body.zones
    ]
    cam.zones = new_zones
    logger.info(
        "Zone config updated | camera_id=%s zones=%d",
        camera_id,
        len(new_zones),
    )

    health_status: dict = {}
    if pipeline.health_monitor:
        health_status = pipeline.health_monitor.get_status()

    return _build_camera_response(cam, health_status.get(camera_id))


# ---------------------------------------------------------------------------
# GET /api/cameras/{camera_id}/stream  (MJPEG)
# ---------------------------------------------------------------------------


@router.get(
    "/{camera_id}/stream",
    summary="MJPEG live stream",
    responses={200: {"content": {"multipart/x-mixed-replace; boundary=frame": {}}}},
)
async def mjpeg_stream(camera_id: str, request: Request) -> StreamingResponse:
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
