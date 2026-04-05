"""Central settings loader combining cameras.yaml + environment variables."""
import os
from pathlib import Path
from backend.config import load_config

class Settings:
    def __init__(self):
        self._config = load_config()
        self.mqtt_broker: str = os.getenv("MQTT_BROKER", self._config.get("global", {}).get("mqtt_broker", "localhost"))
        self.mqtt_port: int = int(os.getenv("MQTT_PORT", self._config.get("global", {}).get("mqtt_port", 1883)))
        self.jwt_secret: str = os.getenv("VANTAG_JWT_SECRET", "dev-secret-change-in-production")
        self.face_key: str = os.getenv("VANTAG_FACE_KEY", "")
        self.env: str = os.getenv("VANTAG_ENV", "development")
        self.snapshots_dir: Path = Path("snapshots")
        self.snapshots_dir.mkdir(exist_ok=True)
        (self.snapshots_dir / "reports").mkdir(exist_ok=True)

settings = Settings()
