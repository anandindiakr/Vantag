"""
backend/api/snapshots_router.py
================================
Authenticated snapshot file serving.

Replaces the unauthenticated ``StaticFiles`` mount for the /snapshots directory.

Endpoints
---------
GET /api/snapshots/{tenant_id}/{camera_id}/{filename}
    Serves a camera snapshot.  Requires a valid JWT whose ``tenant_id`` claim
    matches the ``tenant_id`` path segment.

GET /api/snapshots/watchlist/{filename}
    Serves a watchlist profile image.  Requires a valid JWT (any tenant).

GET /api/snapshots/demo/{filename}
    Serves a demo-mode snapshot.  Requires a valid JWT (any tenant).

Security
--------
* JWT authentication is required on every request.
* Tenant-scoped paths are verified: the JWT ``tenant_id`` must match the path.
* Path traversal is blocked: filenames containing ``..`` or ``/`` are rejected.
* Files outside the snapshots root directory are never served (os.path.realpath check).
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..middleware.tenant_middleware import get_current_user_id

snapshots_router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])

# Root of all snapshot files (same as _SNAPSHOTS_DIR in main.py)
_SNAPSHOTS_ROOT = (
    Path(__file__).resolve().parent.parent.parent / "snapshots"
)


def _safe_path(base: Path, *parts: str) -> Path:
    """
    Resolve *base / parts* and raise 404 if the result escapes *base*
    (path traversal guard).
    """
    try:
        candidate = (base / Path(*parts)).resolve()
    except Exception:
        raise HTTPException(status_code=404, detail="Not found")

    if not str(candidate).startswith(str(base.resolve())):
        raise HTTPException(status_code=404, detail="Not found")
    return candidate


def _reject_traversal(filename: str) -> None:
    """Reject filenames that contain path separators or parent-directory tokens."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=404, detail="Not found")


@snapshots_router.get("/{tenant_id}/{camera_id}/{filename}")
async def get_camera_snapshot(
    tenant_id: str,
    camera_id: str,
    filename: str,
    user: dict = Depends(get_current_user_id),
) -> FileResponse:
    """Serve a camera snapshot — JWT required, tenant-scoped."""
    _reject_traversal(tenant_id)
    _reject_traversal(camera_id)
    _reject_traversal(filename)

    # Tenant isolation: JWT tenant_id must match the path segment
    if user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")

    file_path = _safe_path(_SNAPSHOTS_ROOT, tenant_id, camera_id, filename)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return FileResponse(str(file_path), media_type="image/jpeg")


@snapshots_router.get("/watchlist/{filename}")
async def get_watchlist_snapshot(
    filename: str,
    user: dict = Depends(get_current_user_id),
) -> FileResponse:
    """Serve a watchlist profile image — JWT required."""
    _reject_traversal(filename)

    file_path = _safe_path(_SNAPSHOTS_ROOT, "watchlist", filename)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return FileResponse(str(file_path), media_type="image/jpeg")


@snapshots_router.get("/demo/{filename}")
async def get_demo_snapshot(
    filename: str,
    user: dict = Depends(get_current_user_id),
) -> FileResponse:
    """Serve a demo-mode snapshot — JWT required."""
    _reject_traversal(filename)

    file_path = _safe_path(_SNAPSHOTS_ROOT, "demo", filename)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found")

    return FileResponse(str(file_path), media_type="image/jpeg")
