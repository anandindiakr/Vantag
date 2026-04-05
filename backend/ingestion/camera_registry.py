"""
camera_registry.py
==================
Loads cameras.yaml and provides typed, validated access to camera
configuration throughout the Vantag backend.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    """Raised when the camera configuration is invalid or incomplete."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ZoneConfig:
    """A named region-of-interest polygon within a camera frame."""
    name: str
    points: List[Tuple[int, int]]


@dataclass
class Resolution:
    width: int
    height: int


@dataclass
class CameraConfig:
    """Fully typed representation of a single camera entry from cameras.yaml."""
    id: str
    name: str
    rtsp_url: str
    location: str
    resolution: Resolution
    fps_target: int
    enabled: bool
    low_light_mode: bool
    zones: List[ZoneConfig]
    staff_zone_colors: List[str]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REQUIRED_CAMERA_FIELDS: List[str] = [
    "id", "name", "rtsp_url", "location",
    "resolution", "fps_target", "enabled",
    "low_light_mode", "zones", "staff_zone_colors",
]

_REQUIRED_GLOBAL_FIELDS: List[str] = [
    "mqtt_broker", "mqtt_port", "reconnect_backoff_max",
    "frame_buffer_size", "risk_score_window_seconds",
]

_DEFAULT_CONFIG_PATH: Path = (
    Path(__file__).resolve().parent.parent / "config" / "cameras.yaml"
)


class CameraRegistry:
    """
    Loads and indexes camera configuration from a YAML file.

    Usage
    -----
    >>> registry = CameraRegistry()
    >>> registry.load()
    >>> cam = registry.get_camera("cam-01")
    """

    def __init__(self, config_path: Optional[str | Path] = None) -> None:
        self._config_path: Path = (
            Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        )
        self._cameras: Dict[str, CameraConfig] = {}
        self._global: Dict = {}
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """
        Parse cameras.yaml, validate every entry, and populate the internal
        registry.  Raises ``ConfigError`` on any validation failure.
        """
        if not self._config_path.exists():
            raise ConfigError(
                f"Camera configuration not found: {self._config_path}"
            )

        with self._config_path.open("r", encoding="utf-8") as fh:
            raw: dict = yaml.safe_load(fh)

        if not isinstance(raw, dict):
            raise ConfigError("cameras.yaml must be a YAML mapping at the top level.")

        # ---- global settings ----
        global_raw: dict = raw.get("global", {})
        self._validate_global(global_raw)
        self._global = global_raw

        # ---- per-camera entries ----
        cameras_raw: list = raw.get("cameras", [])
        if not isinstance(cameras_raw, list) or len(cameras_raw) == 0:
            raise ConfigError("cameras.yaml must contain at least one camera under 'cameras'.")

        self._cameras = {}
        for idx, cam_raw in enumerate(cameras_raw):
            cam = self._parse_camera(cam_raw, index=idx)
            if cam.id in self._cameras:
                raise ConfigError(f"Duplicate camera id '{cam.id}' in cameras.yaml.")
            self._cameras[cam.id] = cam

        self._loaded = True

    def get_camera(self, camera_id: str) -> CameraConfig:
        """Return ``CameraConfig`` for the given camera id."""
        self._ensure_loaded()
        if camera_id not in self._cameras:
            raise KeyError(f"No camera with id '{camera_id}' in registry.")
        return self._cameras[camera_id]

    def all_cameras(self) -> List[CameraConfig]:
        """Return a list of all ``CameraConfig`` objects (enabled or not)."""
        self._ensure_loaded()
        return list(self._cameras.values())

    def get_zones(self, camera_id: str) -> List[ZoneConfig]:
        """Return the list of ``ZoneConfig`` objects for the given camera."""
        return self.get_camera(camera_id).zones

    def get_global(self) -> Dict:
        """Return a copy of the parsed global settings dict."""
        self._ensure_loaded()
        return dict(self._global)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise ConfigError(
                "CameraRegistry has not been loaded. Call load() first."
            )

    @staticmethod
    def _validate_global(global_raw: dict) -> None:
        missing = [f for f in _REQUIRED_GLOBAL_FIELDS if f not in global_raw]
        if missing:
            raise ConfigError(
                f"cameras.yaml is missing required global fields: {missing}"
            )

    @staticmethod
    def _parse_camera(raw: dict, index: int) -> CameraConfig:
        """Validate and convert a raw camera dict into a ``CameraConfig``."""
        missing = [f for f in _REQUIRED_CAMERA_FIELDS if f not in raw]
        if missing:
            raise ConfigError(
                f"Camera at index {index} is missing required fields: {missing}"
            )

        cam_id: str = raw["id"]

        # ---- resolution ----
        res_raw = raw["resolution"]
        if not isinstance(res_raw, dict) or "width" not in res_raw or "height" not in res_raw:
            raise ConfigError(
                f"Camera '{cam_id}': 'resolution' must have 'width' and 'height'."
            )
        resolution = Resolution(
            width=int(res_raw["width"]),
            height=int(res_raw["height"]),
        )

        # ---- zones ----
        zones_raw = raw["zones"]
        if not isinstance(zones_raw, list):
            raise ConfigError(f"Camera '{cam_id}': 'zones' must be a list.")
        zones: List[ZoneConfig] = []
        for z in zones_raw:
            if "name" not in z or "points" not in z:
                raise ConfigError(
                    f"Camera '{cam_id}': each zone requires 'name' and 'points'."
                )
            pts = [tuple(p) for p in z["points"]]
            zones.append(ZoneConfig(name=z["name"], points=pts))  # type: ignore[arg-type]

        # ---- staff zone colors ----
        colors = raw["staff_zone_colors"]
        if not isinstance(colors, list):
            raise ConfigError(
                f"Camera '{cam_id}': 'staff_zone_colors' must be a list of hex strings."
            )

        return CameraConfig(
            id=cam_id,
            name=str(raw["name"]),
            rtsp_url=str(raw["rtsp_url"]),
            location=str(raw["location"]),
            resolution=resolution,
            fps_target=int(raw["fps_target"]),
            enabled=bool(raw["enabled"]),
            low_light_mode=bool(raw["low_light_mode"]),
            zones=zones,
            staff_zone_colors=[str(c) for c in colors],
        )
