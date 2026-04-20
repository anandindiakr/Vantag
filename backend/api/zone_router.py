"""
backend/api/zone_router.py
===========================
Zone CRUD endpoints — read and write zone definitions per camera.
Writes update cameras.yaml in-place; pipeline reloads config on next tick.

Zones are stored as JSON so the frontend visual editor can round-trip them
without touching YAML files directly.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..middleware.tenant_middleware import get_current_user_id as get_current_user

router = APIRouter(prefix="/api/zones", tags=["Zones"])

_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "backend" / "config" / "cameras.yaml"
)

# ── Pydantic models ───────────────────────────────────────────────────────────


class BboxZone(BaseModel):
    label:       str
    bbox:        list[int]            # [x1, y1, x2, y2] in pixels
    zone_type:   str = "shelf"        # shelf | queue
    max_queue:   int | None = None    # for queue zones


class PolygonZone(BaseModel):
    name:         str
    polygon:      list[list[int]]     # [[x,y], [x,y], ...]  ≥ 3 points
    severity:     str = "high"
    allowed_hours: list[int] | None = None  # [start_hour, end_hour]


class ZoneConfig(BaseModel):
    shelf_zones:      list[BboxZone]    = []
    restricted_zones: list[PolygonZone] = []
    queue_zones:      list[BboxZone]    = []


class ZoneConfigResponse(BaseModel):
    camera_id:  str
    camera_name: str
    resolution: dict[str, int]
    zones:      ZoneConfig


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_yaml() -> dict[str, Any]:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_yaml(data: dict[str, Any]) -> None:
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def _find_camera(cameras: list[dict], cam_id: str) -> tuple[int, dict]:
    for i, cam in enumerate(cameras):
        if cam.get("id") == cam_id:
            return i, cam
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Camera '{cam_id}' not found in cameras.yaml",
    )


def _parse_zones(cam: dict) -> ZoneConfig:
    """Extract structured zones from a camera's analyzer_config."""
    ac = cam.get("analyzer_config") or {}

    # Shelf zones (from inventory_movement)
    im_cfg    = ac.get("inventory_movement") or {}
    raw_shelf = im_cfg.get("zones") or []
    shelves   = [
        BboxZone(label=z.get("label", "Shelf"), bbox=z["bbox"], zone_type="shelf")
        for z in raw_shelf
        if "bbox" in z
    ]

    # Restricted zones
    rz_cfg     = ac.get("restricted_zone") or {}
    raw_rz     = rz_cfg.get("restricted_zones") or []
    restricted = [
        PolygonZone(
            name=z.get("name", "Zone"),
            polygon=z.get("polygon", []),
            severity=z.get("severity", "high"),
            allowed_hours=z.get("allowed_hours"),
        )
        for z in raw_rz
    ]

    # Queue zones
    ql_cfg     = ac.get("queue_length") or {}
    raw_queue  = ql_cfg.get("queue_zones") or []
    queues     = [
        BboxZone(
            label=z.get("label", "Queue"),
            bbox=z["bbox"],
            zone_type="queue",
            max_queue=z.get("max_queue"),
        )
        for z in raw_queue
        if "bbox" in z
    ]

    return ZoneConfig(
        shelf_zones=shelves,
        restricted_zones=restricted,
        queue_zones=queues,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/cameras/{cam_id}",
    response_model=ZoneConfigResponse,
    summary="Get zone configuration for a camera",
)
async def get_zones(
    cam_id: str,
    _: dict = Depends(get_current_user),
) -> ZoneConfigResponse:
    data    = _load_yaml()
    cameras = data.get("cameras") or []
    _, cam  = _find_camera(cameras, cam_id)
    res     = cam.get("resolution") or {}

    return ZoneConfigResponse(
        camera_id=cam_id,
        camera_name=cam.get("name", cam_id),
        resolution={
            "width":  res.get("width", 1920),
            "height": res.get("height", 1080),
        },
        zones=_parse_zones(cam),
    )


@router.put(
    "/cameras/{cam_id}",
    response_model=ZoneConfigResponse,
    summary="Save zone configuration for a camera",
    description=(
        "Writes new zone definitions to cameras.yaml. "
        "The pipeline reloads zone config automatically within 5 seconds."
    ),
)
async def save_zones(
    cam_id: str,
    body:   ZoneConfig,
    _:      dict = Depends(get_current_user),
) -> ZoneConfigResponse:
    data    = _load_yaml()
    cameras = data.get("cameras") or []
    idx, cam = _find_camera(cameras, cam_id)
    cam = copy.deepcopy(cam)

    # Ensure analyzer_config exists
    if "analyzer_config" not in cam or cam["analyzer_config"] is None:
        cam["analyzer_config"] = {}
    ac = cam["analyzer_config"]

    # -- Shelf zones → inventory_movement.zones --
    if "inventory_movement" not in ac or ac["inventory_movement"] is None:
        ac["inventory_movement"] = {
            "drop_threshold": 2,
            "check_interval_seconds": 5.0,
            "cooldown_seconds": 20,
            "person_suppression": True,
        }
    ac["inventory_movement"]["zones"] = [
        {"label": z.label, "bbox": z.bbox}
        for z in body.shelf_zones
    ]

    # -- Restricted zones → restricted_zone.restricted_zones --
    if "restricted_zone" not in ac or ac["restricted_zone"] is None:
        ac["restricted_zone"] = {"cooldown_seconds": 15, "min_frames_inside": 2}
    ac["restricted_zone"]["restricted_zones"] = [
        {
            "name": z.name,
            "polygon": z.polygon,
            "severity": z.severity,
            **({"allowed_hours": z.allowed_hours} if z.allowed_hours else {}),
        }
        for z in body.restricted_zones
    ]

    # -- Queue zones → queue_length.queue_zones --
    if "queue_length" not in ac or ac["queue_length"] is None:
        ac["queue_length"] = {
            "alert_threshold": 5,
            "check_interval_seconds": 3.0,
            "cooldown_seconds": 60,
        }
    ac["queue_length"]["queue_zones"] = [
        {
            "label": z.label,
            "bbox":  z.bbox,
            "max_queue": z.max_queue or 5,
        }
        for z in body.queue_zones
    ]

    cam["analyzer_config"] = ac
    data["cameras"][idx]   = cam
    _save_yaml(data)

    res = cam.get("resolution") or {}
    return ZoneConfigResponse(
        camera_id=cam_id,
        camera_name=cam.get("name", cam_id),
        resolution={
            "width":  res.get("width", 1920),
            "height": res.get("height", 1080),
        },
        zones=_parse_zones(cam),
    )
