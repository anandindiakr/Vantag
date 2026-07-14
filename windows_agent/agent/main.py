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

# ── Minimise console window on Windows (runs as tray app) ────────────────────
def _hide_console() -> None:
    """Minimise the cmd window immediately — agent lives in the system tray."""
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
    except Exception:  # noqa: BLE001
        pass  # non-Windows or ctypes unavailable — ignore

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
        cameras = discovery.run_discovery(
            scan_subnet=_config.scan_subnet or None,
        )
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



def _run_rtsp_probe_job(job: dict):
    """Run a cloud-delegated RTSP path probe on this LAN and report back.

    The cloud cannot reach private camera IPs, so the dashboard's
    "Auto-Detect RTSP path" queues a job that we execute here.
    """
    if _api is None:
        return
    job_id = job.get("job_id")
    ip = job.get("ip")
    port = int(job.get("port") or 554)
    username = job.get("username") or None
    password = job.get("password") or None
    brand = job.get("brand") or None
    log.info("RTSP probe job %s: %s:%s (brand=%s)", job_id, ip, port, brand)

    tried: list[str] = []
    result: dict | None = None
    try:
        creds = [(username, password)] if (username or password) else None
        paths = discovery._candidate_paths(brand)
        for path in paths:
            tried.append(path)
            for u, p in (creds or discovery._DEFAULT_CREDS):
                res = discovery._try_rtsp(ip, port, path, u, p)
                if res:
                    result = res
                    break
            if result:
                break
    except Exception as e:  # noqa: BLE001
        log.warning("RTSP probe job %s failed: %s", job_id, e)

    payload = {
        "job_id": job_id,
        "success": result is not None,
        "rtsp_path": result["path"] if result else None,
        "rtsp_url": result["rtsp_url"] if result else None,
        "brand": brand,
        "tried_paths": tried[:50],
        "error": None if result else "No candidate RTSP path produced a video frame. Check IP, port and credentials.",
    }
    try:
        resp = _api._session.post(
            f"{_api.base_url}/api/edge/rtsp-probe-result",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        log.info("RTSP probe job %s reported (success=%s)", job_id, payload["success"])
    except Exception as e:  # noqa: BLE001
        log.warning("Failed to report RTSP probe result %s: %s", job_id, e)


def _on_event(event: dict):
    _recent_events.append(event)
    if len(_recent_events) > 100:
        _recent_events.pop(0)
    log.info(f"EVENT [{event['event_type']}] cam={event['camera_id']} conf={event['confidence']}")


def _map_remote_camera(c: dict) -> CameraConfig:
    """Map a backend camera dict (camera_id/resolution_width/...) to the agent's CameraConfig."""
    analyzer = c.get("analyzer_config") or {}
    conf = c.get("confidence_threshold")
    if conf is None:
        conf = analyzer.get("confidence_threshold")
    try:
        conf = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf = None
    return CameraConfig(
        id=c.get("camera_id") or c.get("id") or "",
        name=c.get("name") or c.get("camera_id") or "Camera",
        rtsp_url=c.get("rtsp_url", ""),
        location=c.get("location", ""),
        enabled=c.get("enabled", True),
        width=c.get("resolution_width") or c.get("width") or 1280,
        height=c.get("resolution_height") or c.get("height") or 720,
        confidence=conf,
    )


def _cam_conf(cam) -> float:
    """Resolve the effective confidence threshold for a camera."""
    val = getattr(cam, "confidence", None)
    if val is None:
        return _config.confidence_threshold
    # Clamp to a sane operating range.
    return max(0.1, min(0.95, float(val)))


def _build_worker(cam):
    return CameraWorker(
        config=cam,
        inference=_inference,
        api_client=_api,
        conf_threshold=_cam_conf(cam),
        target_fps=_config.inference_fps,
        event_cooldown_sec=_config.event_cooldown_sec,
        on_event=_on_event,
    )


def reconcile_cameras():
    """Pull the latest camera list from the backend and start/stop workers so
    that cameras added, removed, enabled or disabled in the web dashboard take
    effect on a running agent WITHOUT requiring a restart."""
    global _workers, _inference
    if _api is None:
        return
    try:
        remote = _api.get_config()
    except Exception as e:  # noqa: BLE001
        log.debug(f"reconcile_cameras: get_config failed: {e}")
        return
    if not remote:
        return

    cams = [_map_remote_camera(c) for c in remote.get("cameras", [])]
    _config.cameras = cams
    try:
        _config.save()
    except Exception:  # noqa: BLE001
        pass

    desired = {
        c.id: c for c in cams
        if c.enabled and (c.rtsp_url or "").strip()
    }
    # Drop workers whose thread has died (e.g. crashed) so they are treated
    # as "not running" below and get restarted automatically.
    for w in list(_workers):
        t = getattr(w, "_thread", None)
        if t is not None and not t.is_alive():
            log.warning(
                f"Worker for camera {w.config.id} is dead — scheduling restart"
            )
            try:
                w.stop()
            except Exception:  # noqa: BLE001
                pass
            _workers.remove(w)

    running = {w.config.id: w for w in _workers}

    # Stop workers whose camera was removed/disabled or whose stream/sensitivity changed.
    for cam_id, w in list(running.items()):
        changed = (
            cam_id not in desired
            or desired[cam_id].rtsp_url != w.config.rtsp_url
            or _cam_conf(desired[cam_id]) != getattr(w, "_conf", None)
        )
        if changed:
            log.info(f"Stopping worker for camera {cam_id} (removed/changed)")
            try:
                w.stop()
            except Exception:  # noqa: BLE001
                pass
            if w in _workers:
                _workers.remove(w)
            running.pop(cam_id, None)

    # Start workers for newly added/confirmed cameras.
    new_ids = [cid for cid in desired if cid not in running]
    if new_ids and _inference is None:
        _inference = YoloInference(device=_config.inference_device)
    for cid in new_ids:
        cam = desired[cid]
        log.info(f"Starting worker for newly added camera '{cam.name}' ({cid})")
        w = _build_worker(cam)
        w.start()
        _workers.append(w)
    if new_ids:
        log.info(f"Camera sync: {len(_workers)} worker(s) now active")


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
            conf_threshold=_cam_conf(cam),
            target_fps=_config.inference_fps,
            event_cooldown_sec=_config.event_cooldown_sec,
            on_event=_on_event,
        )
        worker.start()
        _workers.append(worker)
        # Stagger connects: all cameras share one NVR, which caps concurrent
        # RTSP session setups — simultaneous opens make several fail at once.
        time.sleep(1.0)

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
        # Backend may delegate RTSP path probes (cloud can't reach LAN IPs)
        if isinstance(resp, dict):
            for _job in resp.get("rtsp_probe_jobs") or []:
                threading.Thread(
                    target=_run_rtsp_probe_job,
                    args=(_job,),
                    daemon=True,
                    name=f"rtsp-probe-{_job.get('job_id', '?')[:8]}",
                ).start()

    schedule.every(30).seconds.do(send_heartbeat)
    # Periodically reconcile the camera list with the dashboard so cameras the
    # user adds/removes online start/stop monitoring without an agent restart.
    schedule.every(20).seconds.do(reconcile_cameras)
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

    # Minimise the console immediately — the agent lives in the system tray.
    _hide_console()

    log.info("=" * 60)
    try:
        from . import __version__ as _ver
    except Exception:
        _ver = "unknown"
    log.info(f"Vantag Windows Edge Agent v{_ver} starting")
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

    # Always (re-)register on startup so the backend has the correct
    # platform, hostname and OS version — fixes agents provisioned via
    # QR pairing showing up as "android".
    log.info("Registering agent with backend…")
    try:
        result = _api.register(device_type="windows")
        new_id = result.get("agent_id")
        if new_id and new_id != _config.agent_id:
            _config.agent_id = new_id
            _config.save()
        log.info(f"Agent registered: {_config.agent_id}")
    except Exception as e:
        if not _config.agent_id:
            log.error(f"Registration failed: {e}")
            sys.exit(1)
        log.warning(f"Re-registration failed (continuing with saved agent_id): {e}")

    # Auto-start monitoring
    start_monitoring()

    # First-boot convenience: run one LAN camera discovery scan in the background.
    # Skipped when cameras are already configured — the scan probes the NVR with
    # default credentials, which eats its limited RTSP session slots right when
    # the real workers are trying to connect (and creates disc-* duplicates).
    if not _config.cameras:
        threading.Thread(
            target=run_discovery_and_report,
            args=("startup",),
            daemon=True,
            name="discovery-startup",
        ).start()
    else:
        log.info(
            f"{len(_config.cameras)} camera(s) already configured — "
            "skipping startup discovery scan (use dashboard Auto-Scan if needed)."
        )

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
