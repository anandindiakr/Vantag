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
        self._session.headers["X-Agent-Key"] = api_key

    def register(self, device_type: str = "windows") -> dict:
        """Register this agent with the backend and get full config."""
        import platform
        resp = self._session.post(
            f"{self.base_url}/api/edge/register",
            json={
                "api_key": self.api_key,
                "device_type": device_type,
                "device_model": platform.node(),
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

    def heartbeat(self, status: dict) -> bool:
        """Send agent heartbeat. Returns True on success."""
        try:
            resp = self._session.post(
                f"{self.base_url}/api/edge/heartbeat",
                json=status,
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            log.warning(f"heartbeat failed: {e}")
            return False

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
