"""
camera_registry.py
==================
Loads cameras.yaml and provides typed, validated access to camera
configuration throughout the Vantag backend.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


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
    analyzer_config: Dict = field(default_factory=dict)
    """Optional per-camera config for the AI analyzer stack (zones, thresholds, etc.)."""


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

_DEFAULT_CONFIG_PATH: Path = Path(
    os.environ.get("VANTAG_CAMERAS_YAML")
    or (Path(__file__).resolve().parent.parent / "config" / "cameras.yaml")
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
        # Allow empty camera list for SaaS mode (cameras added later via API/edge agent)
        cameras_raw: list = raw.get("cameras") or []
        if not isinstance(cameras_raw, list):
            raise ConfigError("cameras.yaml 'cameras' must be a list.")

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

    # ------------------------------------------------------------------
    # Mutation API (runtime add/remove + YAML persistence)
    # ------------------------------------------------------------------

    def add_camera(self, cam: CameraConfig) -> None:
        """
        Register a new camera at runtime and persist to YAML.

        Raises ``ConfigError`` if a camera with the same id already exists.
        """
        self._ensure_loaded()
        if cam.id in self._cameras:
            raise ConfigError(f"Camera id '{cam.id}' already exists in registry.")
        self._cameras[cam.id] = cam
        logger.info("Camera added to registry | camera_id=%s", cam.id)
        self.persist_to_yaml()

    def remove_camera(self, camera_id: str) -> CameraConfig:
        """
        Remove a camera from the registry and persist to YAML.

        Returns the removed ``CameraConfig``.
        Raises ``KeyError`` if the camera does not exist.
        """
        self._ensure_loaded()
        if camera_id not in self._cameras:
            raise KeyError(f"No camera with id '{camera_id}' in registry.")
        cam = self._cameras.pop(camera_id)
        logger.info("Camera removed from registry | camera_id=%s", camera_id)
        self.persist_to_yaml()
        return cam

    def persist_to_yaml(self) -> None:
        """
        Write the current in-memory registry state back to the YAML config file.

        Preserves the ``global:`` block and rewrites the ``cameras:`` list.
        Uses ``VANTAG_CAMERAS_YAML`` env var path if set.
        """
        target = Path(
            os.environ.get("VANTAG_CAMERAS_YAML") or self._config_path
        )

        cameras_list: List[dict] = []
        for cam in self._cameras.values():
            cam_dict: dict = {
                "id": cam.id,
                "name": cam.name,
                "rtsp_url": cam.rtsp_url,
                "location": cam.location,
                "resolution": {
                    "width": cam.resolution.width,
                    "height": cam.resolution.height,
                },
                "fps_target": cam.fps_target,
                "enabled": cam.enabled,
                "low_light_mode": cam.low_light_mode,
                "zones": [
                    {"name": z.name, "points": [list(p) for p in z.points]}
                    for z in cam.zones
                ],
                "staff_zone_colors": cam.staff_zone_colors,
                "analyzer_config": cam.analyzer_config,
            }
            cameras_list.append(cam_dict)

        full_doc: dict = {"global": dict(self._global), "cameras": cameras_list}

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(full_doc, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)
            logger.info("cameras.yaml persisted | path=%s cameras=%d", target, len(cameras_list))
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to persist cameras.yaml | error=%s", exc)
            raise

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
            analyzer_config=dict(raw.get("analyzer_config", {})),
        )
