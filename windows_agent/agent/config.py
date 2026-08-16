"""
Config loader for Vantag Windows Edge Agent.
Reads from %APPDATA%/Vantag/config.json
Falls back to vantag_config.json in the executable directory.
"""
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "Vantag"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class CameraConfig:
    id: str
    name: str
    rtsp_url: str
    location: str = ""
    enabled: bool = True
    width: int = 1280
    height: int = 720
    # Per-camera detection confidence threshold (0.25–0.85). When None the
    # agent falls back to the global AgentConfig.confidence_threshold.
    confidence: Optional[float] = None
    people_count_zones: list[dict] = field(default_factory=list)
    # ROI masking: polygon/bbox areas to EXCLUDE from all detection (e.g. a
    # public sidewalk visible through a window, a TV/mirror reflecting
    # people, or a neighboring aisle out of scope). Any detection box whose
    # center falls inside one of these zones is dropped before it can
    # trigger a shoplifting/restricted-zone/loitering event or be counted.
    exclusion_zones: list[dict] = field(default_factory=list)
    # Shelf/inventory-movement zones (drawn in the Zone Editor's Shelf type).
    # Fed into DetectionAnalyzer's InventoryMovementDetector so item removal/
    # rearrangement inside these areas is actually evaluated by the edge
    # agent — previously configured but never delivered here, so it had no
    # effect at all.
    inventory_zones: list[dict] = field(default_factory=list)
    # High-Value Counter (jewellery / luxury goods) scene profile, delivered
    # by the backend's /api/edge/config response as "high_value_counter".
    # Structure: {"jewelry_handover": {...}, "jewelry_tray": {...},
    # "grab_and_run": {...}} with polygon vertices normalized to 0-1
    # fractions of the camera's reference resolution.
    high_value_counter: dict = field(default_factory=dict)
    # Per-camera opt-in analytic toggles, delivered by the backend's
    # /api/edge/config response as "detections". Keys: shoplifting,
    # loitering, suspicious_behavior, crowding, fall_detected,
    # people_count. The backend applies the same gate authoritatively on
    # ingest, so honouring it here does not change WHICH events reach the
    # dashboard — it just stops us burning CPU on every camera running
    # heuristics whose results would only be discarded server-side.
    detections: dict = field(default_factory=dict)


@dataclass
class AgentConfig:
    api_key: str = ""
    agent_id: str = ""
    backend_url: str = "https://retail-vantag.com"
    mqtt_host: str = "retail-vantag.com"
    # The production Mosquitto broker listens on 1883 (plain TCP) and 9001
    # (WebSocket). Use 8883 only when a TLS listener has been configured on
    # the broker; the agent auto-enables TLS when the port is 8883.
    mqtt_port: int = 1883
    mqtt_username: str = "vantag_edge"  # shared edge broker user
    mqtt_password: str = ""             # shared edge broker password (falls back to api_key)
    tenant_id: str = ""
    # Door / access-control relay configuration. Structure:
    #   {"relay_type": "simulate"|"http"|"gpio", "http_url": "...", "gpio_pin": 17}
    # "simulate" (default) logs and reports status without physical hardware.
    door_control: dict = field(default_factory=dict)
    cameras: List[CameraConfig] = field(default_factory=list)
    inference_device: str = "cpu"       # "cpu" | "cuda" | "dml"
    inference_fps: int = 5              # target inference FPS per camera
    confidence_threshold: float = 0.6
    event_cooldown_sec: int = 30        # min seconds between same event type per camera
    log_level: str = "INFO"
    # Set to e.g. "192.168.254.0/24" to force discovery onto a specific LAN.
    # Leave blank to auto-detect all private (RFC-1918) subnets.
    scan_subnet: str = ""

    @classmethod
    def load(cls) -> "AgentConfig":
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # 1) The pre-filled config.json shipped NEXT TO the agent package is
        #    regenerated on every download with the current api_key + MQTT
        #    credentials, so it is authoritative. It used to lose to the
        #    %APPDATA% cache, which meant re-downloading a new build silently
        #    kept stale/empty MQTT credentials — the agent then fell back to
        #    using the api_key as the broker password and got "MQTT connect
        #    error rc=5" (not authorised) forever.
        # 2) The %APPDATA% config only carries locally-tuned / runtime-updated
        #    fields (door_control pushed from the dashboard wizard, scan_subnet,
        #    inference overrides), so those are merged back on top.
        local_cfg = Path(__file__).resolve().parent.parent / "config.json"

        def _load(path: Path) -> Optional["AgentConfig"]:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                cams = [CameraConfig(**c) for c in raw.pop("cameras", [])]
                return cls(**raw, cameras=cams)
            except Exception as e:  # noqa: BLE001
                print(f"[Config] Failed to load config from {path}: {e}")
                return None

        bundled = _load(local_cfg) if local_cfg.exists() else None
        user = _load(CONFIG_FILE) if CONFIG_FILE.exists() else None

        if bundled is not None and bundled.api_key:
            if user is not None:
                # Preserve fields that are only ever set locally or at runtime;
                # the download bundle intentionally does not ship them.
                for field in (
                    "door_control",
                    "scan_subnet",
                    "inference_device",
                    "inference_fps",
                    "confidence_threshold",
                    "event_cooldown_sec",
                    "log_level",
                ):
                    value = getattr(user, field, None)
                    if value:
                        setattr(bundled, field, value)
            return bundled

        if user is not None:
            return user

        return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[Config] Saved to {CONFIG_FILE}")

    def is_configured(self) -> bool:
        # Only api_key is required for first-run.
        # agent_id is assigned by the backend after registration.
        return bool(self.api_key)
