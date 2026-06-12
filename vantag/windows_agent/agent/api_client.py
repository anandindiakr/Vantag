"""
HTTP client for posting events and heartbeats to Vantag backend.
Uses requests with retry logic and connection pooling.
"""
import logging
import time
from typing import Optional
import requests
from requests.adapters import HTTPAdapter, Retry

log = logging.getLogger("vantag.api")


def _build_session(base_url: str) -> requests.Session:
    sess = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    sess.headers.update({
        "Content-Type": "application/json",
        "User-Agent": "VantagWindowsAgent/1.0",
    })
    return sess


class VantagApiClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._session = _build_session(base_url)
        self._session.headers["X-API-Key"] = api_key

    def register(self, device_type: str = "windows") -> dict:
        """Register this agent with the backend and get full config."""
        import platform
        resp = self._session.post(
            f"{self.base_url}/api/edge/register",
            json={
                "api_key": self.api_key,
                "device_type": device_type,
                "device_name": platform.node(),
                "os_version": platform.version(),
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    def post_event(self, event: dict) -> bool:
        """Post a detection event. Returns True on success."""
        try:
            resp = self._session.post(
                f"{self.base_url}/api/edge/events",
                json=event,
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            log.warning(f"post_event failed: {e}")
            return False

    def post_preview(self, camera_id: str, frame_b64: str) -> bool:
        """Push a periodic live-preview JPEG (base64) so the cloud dashboard can
        render a near-real-time still. Best-effort; failures are non-fatal.
        """
        try:
            resp = self._session.post(
                f"{self.base_url}/api/edge/preview",
                json={"camera_id": camera_id, "frame_b64": frame_b64},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as e:  # noqa: BLE001
            log.debug(f"post_preview failed: {e}")
            return False

    def heartbeat(self, status: dict) -> Optional[dict]:
        """Send agent heartbeat. Returns the parsed response dict, or None on failure.

        The response may include a ``scan_requested`` flag that the agent uses to
        trigger an on-demand camera discovery scan.
        """
        try:
            resp = self._session.post(
                f"{self.base_url}/api/edge/heartbeat",
                json=status,
                timeout=10,
            )
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:  # noqa: BLE001
                return {}
        except Exception as e:
            log.warning(f"heartbeat failed: {e}")
            return None

    def report_discovered(self, cameras: list) -> Optional[dict]:
        """Report auto-discovered LAN cameras to the backend.

        POSTs to ``/api/edge/cameras/discovered`` with the X-API-Key session.
        Returns the parsed response dict, or None on failure.
        """
        try:
            resp = self._session.post(
                f"{self.base_url}/api/edge/cameras/discovered",
                json={"cameras": cameras},
                timeout=30,
            )
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:  # noqa: BLE001
                return {}
        except Exception as e:
            log.warning(f"report_discovered failed: {e}")
            return None

    def get_config(self) -> Optional[dict]:
        """Fetch latest config from backend."""
        try:
            resp = self._session.get(
                f"{self.base_url}/api/edge/config",
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            log.warning(f"get_config failed: {e}")
            return None
