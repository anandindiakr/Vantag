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


@dataclass
class AgentConfig:
    api_key: str = ""
    agent_id: str = ""
    backend_url: str = "https://app.vantag.io"
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    tenant_id: str = ""
    cameras: List[CameraConfig] = field(default_factory=list)
    inference_device: str = "cpu"       # "cpu" | "cuda" | "dml"
    inference_fps: int = 5              # target inference FPS per camera
    confidence_threshold: float = 0.6
    event_cooldown_sec: int = 30        # min seconds between same event type per camera
    log_level: str = "INFO"

    @classmethod
    def load(cls) -> "AgentConfig":
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        if CONFIG_FILE.exists():
            try:
                raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
                cams = [CameraConfig(**c) for c in raw.pop("cameras", [])]
                return cls(**raw, cameras=cams)
            except Exception as e:
                print(f"[Config] Failed to load config: {e} — using defaults")
        return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = asdict(self)
        CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[Config] Saved to {CONFIG_FILE}")

    def is_configured(self) -> bool:
        return bool(self.api_key and self.agent_id)
