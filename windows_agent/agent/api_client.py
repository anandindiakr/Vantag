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
    # Best-effort posts (events/frames) must NOT hog connections with long
    # retry backoffs — that starves the pool when many cameras post at once.
    retry = Retry(
        total=1,
        backoff_factor=0.3,
        status_forcelist=[502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    # An NVR with many channels means many CameraWorker threads each pushing
    # frames every 0.2s over this single shared session. The default urllib3
    # pool is only 10 connections, which gets exhausted under that load and
    # silently drops frame pushes ("Connection pool is full"), which is why
    # the dashboard can show the agent "online" (heartbeat gets a slot) but
    # never receives a live frame. Give every worker headroom.
    adapter = HTTPAdapter(max_retries=retry, pool_connections=32, pool_maxsize=32)
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
                timeout=(3.05, 5),
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            log.warning(f"post_event failed: {e}")
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

    def push_frame(self, camera_id: str, frame_b64: str) -> bool:
        """Push a JPEG frame (base64) to the backend live-relay cache.

        Best-effort, low-timeout, fire-and-forget style call used to keep the
        cloud dashboard's live view working when the backend cannot reach the
        camera's RTSP stream directly (e.g. camera on a private LAN behind
        the customer's router). Failures are logged at debug level only —
        this must never block or crash the capture loop.
        """
        try:
            resp = self._session.post(
                f"{self.base_url}/api/edge/frame",
                json={"camera_id": camera_id, "frame_b64": frame_b64},
                timeout=(3.05, 5),
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            log.debug(f"push_frame failed for {camera_id}: {e}")
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
