"""Central settings loader combining cameras.yaml + environment variables."""
import os
from pathlib import Path
from backend.config import load_config

# Load .env file if present (for local development / live testing)
try:
    from dotenv import load_dotenv
    _env_file = Path(__file__).resolve().parent.parent.parent / ".env"
    if _env_file.exists():
        load_dotenv(_env_file, override=False)
except ImportError:
    pass


class Settings:
    def __init__(self):
        self._config = load_config()
        self.mqtt_broker: str = os.getenv("MQTT_BROKER", self._config.get("global", {}).get("mqtt_broker", "localhost"))
        self.mqtt_port: int = int(os.getenv("MQTT_PORT", self._config.get("global", {}).get("mqtt_port", 1883)))
        self.jwt_secret: str = os.getenv("VANTAG_JWT_SECRET", "dev-secret-change-in-production")
        self.face_key: str = os.getenv("VANTAG_FACE_KEY", "")
        self.env: str = os.getenv("VANTAG_ENV", "development")
        self.face_recognition_enabled: bool = os.getenv("VANTAG_FACE_RECOGNITION", "true").lower() == "true"
        self.postgres_url: str = os.getenv("POSTGRES_URL", "")
        self.snapshots_dir: Path = Path("snapshots")
        self.snapshots_dir.mkdir(exist_ok=True)
        (self.snapshots_dir / "reports").mkdir(exist_ok=True)

settings = Settings()
