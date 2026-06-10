"""
Vantag Windows Edge Agent — main entry point.

Responsibilities:
  1. Load config from %APPDATA%/Vantag/config.json
  2. If not configured, open browser to /onboarding for setup
  3. Register with Vantag backend (get agent_id + camera list)
  4. Start per-camera RTSP worker threads
  5. Start MQTT client for door control
  6. Run periodic heartbeat
  7. Show system tray icon
"""
import logging
import os
import sys
import time
import threading
import webbrowser
import schedule

from .config import AgentConfig
from .api_client import VantagApiClient
from .mqtt_client import VantagMqttClient
from .camera_worker import CameraWorker, CameraConfig
from .inference import YoloInference
from .tray_icon import VantagTrayIcon
from . import discovery

# ── Logging setup ────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Vantag")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "agent.log"), encoding="utf-8"),
    ],
)
log = logging.getLogger("vantag.main")


# ── Global state ──────────────────────────────────────────────────────────────
_config: AgentConfig = None
_api: VantagApiClient = None
_mqtt: VantagMqttClient = None
_inference: YoloInference = None
_workers: list[CameraWorker] = []
_recent_events: list[dict] = []   # in-memory event log for tray tooltip
_scan_lock = threading.Lock()     # guards against concurrent discovery scans


def run_discovery_and_report(reason: str = "startup"):
    """Run a LAN camera discovery scan and POST results to the backend.

    Runs in a background thread. Guarded by ``_scan_lock`` so overlapping
    triggers (startup + scan_requested) never run two scans at once.
    """
    if _api is None:
        return
    if not _scan_lock.acquire(blocking=False):
        log.info("Discovery scan already running — skipping %s trigger", reason)
        return
    try:
        log.info("Camera discovery scan started (%s)…", reason)
        cameras = discovery.run_discovery()
        log.info("Discovery found %d candidate camera(s)", len(cameras))
        resp = _api.report_discovered(cameras)
        if resp is None:
            log.warning("Failed to report discovered cameras to backend")
        else:
            log.info("Reported %d discovered camera(s) to backend", len(cameras))
    except Exception as e:  # noqa: BLE001
        log.warning("Discovery scan failed: %s", e)
    finally:
        _scan_lock.release()



def _on_event(event: dict):
    _recent_events.append(event)
    if len(_recent_events) > 100:
        _recent_events.pop(0)
    log.info(f"EVENT [{event['event_type']}] cam={event['camera_id']} conf={event['confidence']}")


def _map_remote_camera(c: dict) -> CameraConfig:
    """Map a backend camera dict (camera_id/resolution_width/...) to the agent's CameraConfig."""
    return CameraConfig(
        id=c.get("camera_id") or c.get("id") or "",
        name=c.get("name") or c.get("camera_id") or "Camera",
        rtsp_url=c.get("rtsp_url", ""),
        location=c.get("location", ""),
        enabled=c.get("enabled", True),
        width=c.get("resolution_width") or c.get("width") or 1280,
        height=c.get("resolution_height") or c.get("height") or 720,
    )


def start_monitoring():
    global _workers, _inference, _mqtt

    log.info("Starting monitoring…")

    # Load or refresh config from backend
    remote = _api.get_config()
    if remote and remote.get("cameras"):
        cams = [_map_remote_camera(c) for c in remote["cameras"]]
        _config.cameras = cams
        _config.save()

    if not _config.cameras:
        log.warning("No cameras configured. Complete setup via the web dashboard.")
        return

    # Load inference model
    _inference = YoloInference(device=_config.inference_device)

    # Start per-camera workers
    _workers = []
    for cam in _config.cameras:
        if not cam.enabled:
            continue
        if not (cam.rtsp_url or "").strip():
            log.info(
                f"Skipping camera '{cam.name}' ({cam.id}) — no RTSP URL configured. "
                f"Add a stream URL via the dashboard to start monitoring it."
            )
            continue
        worker = CameraWorker(
            config=cam,
            inference=_inference,
            api_client=_api,
            conf_threshold=_config.confidence_threshold,
            target_fps=_config.inference_fps,
            event_cooldown_sec=_config.event_cooldown_sec,
            on_event=_on_event,
        )
        worker.start()
        _workers.append(worker)

    log.info(f"Started {len(_workers)} camera workers")

    # MQTT
    _mqtt = VantagMqttClient(
        host=_config.mqtt_host,
        port=_config.mqtt_port,
        tenant_id=_config.tenant_id,
        api_key=_config.api_key,
        username=getattr(_config, "mqtt_username", "vantag_edge"),
        password=getattr(_config, "mqtt_password", ""),
    )
    _mqtt.connect()

    # Heartbeat scheduler
    def send_heartbeat():
        if _api is None:
            return
        import psutil
        camera_statuses = {}
        fps_per_camera = {}
        for w in _workers:
            cam_id = w.config.id
            camera_statuses[cam_id] = "online" if w.is_connected else "offline"
            fps_per_camera[cam_id] = round(w.current_fps, 1)
        resp = _api.heartbeat({
            "camera_statuses": camera_statuses,
            "fps_per_camera": fps_per_camera,
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory_percent": psutil.virtual_memory().percent,
        })
        # Backend may request an on-demand LAN camera scan
        if isinstance(resp, dict) and resp.get("scan_requested"):
            threading.Thread(
                target=run_discovery_and_report,
                args=("scan_requested",),
                daemon=True,
                name="discovery-ondemand",
            ).start()

    schedule.every(30).seconds.do(send_heartbeat)
    threading.Thread(
        target=lambda: [time.sleep(1) or schedule.run_pending() for _ in iter(int, 1)],
        daemon=True,
        name="heartbeat",
    ).start()


def stop_monitoring():
    global _workers, _mqtt
    log.info("Stopping monitoring…")
    for w in _workers:
        w.stop()
    _workers.clear()
    if _mqtt:
        _mqtt.disconnect()
        _mqtt = None
    log.info("Monitoring stopped")


def open_settings():
    webbrowser.open(f"{_config.backend_url}/onboarding")


def main():
    global _config, _api

    log.info("=" * 60)
    log.info("Vantag Windows Edge Agent v1.0.0 starting")
    log.info("=" * 60)

    _config = AgentConfig.load()

    if not _config.is_configured():
        log.warning("Agent not configured. Opening browser for setup…")
        webbrowser.open(f"{_config.backend_url}")
        # Wait for user to complete onboarding and save config
        log.info("Waiting for config (check %APPDATA%\\Vantag\\config.json after setup)…")
        # Poll for config every 5 seconds
        for _ in range(120):  # wait up to 10 minutes
            time.sleep(5)
            _config = AgentConfig.load()
            if _config.is_configured():
                break
        if not _config.is_configured():
            log.error("Setup not completed within 10 minutes. Exiting.")
            sys.exit(1)

    # Register / validate with backend
    _api = VantagApiClient(base_url=_config.backend_url, api_key=_config.api_key)

    if not _config.agent_id:
        log.info("Registering agent with backend…")
        try:
            result = _api.register(device_type="windows")
            _config.agent_id = result["agent_id"]
            _config.save()
            log.info(f"Agent registered: {_config.agent_id}")
        except Exception as e:
            log.error(f"Registration failed: {e}")
            sys.exit(1)

    # Auto-start monitoring
    start_monitoring()

    # First-boot convenience: run one LAN camera discovery scan in the background
    threading.Thread(
        target=run_discovery_and_report,
        args=("startup",),
        daemon=True,
        name="discovery-startup",
    ).start()

    # System tray
    tray = VantagTrayIcon(
        on_start=start_monitoring,
        on_stop=stop_monitoring,
        on_settings=open_settings,
        on_quit=lambda: sys.exit(0),
        dashboard_url=_config.backend_url,
    )
    log.info("Vantag tray icon running. Right-click tray icon to control.")
    tray.run()   # blocks until tray icon quits


if __name__ == "__main__":
    main()
