from __future__ import annotations

import hashlib
import json
import logging
import socket
import threading
import time
import uuid
import webbrowser
from pathlib import Path

from .hardware import verify_assets
from .licensing import LicenceManager
from .runtime import LocalRuntime
from .server import create_app
from .store import SiteStore

_lock = threading.RLock()
_server = None
_thread = None
_runtime = None
_url = ""
_last_error = ""


def _device_id(store: SiteStore) -> str:
    import winreg
    from .vault import protect, unprotect
    protected = store.get("installation_id")
    if protected:
        installation = unprotect(protected)
    else:
        installation = str(uuid.uuid4())
        store.set("installation_id", protect(installation))
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        machine = winreg.QueryValueEx(key, "MachineGuid")[0]
    return hashlib.sha256(f"{machine}:{installation}".encode()).hexdigest()


def _run() -> None:
    global _server, _runtime, _url, _last_error
    listener = None
    try:
        import uvicorn
        from ultralytics import settings
        from ..resources import application_directory, bundled_resource

        settings.update({"sync": False, "clearml": False, "comet": False, "dvc": False, "mlflow": False, "raytune": False, "tensorboard": False, "wandb": False})
        store = SiteStore(Path.home() / ".vantag" / "offline-site")
        logging.basicConfig(filename=store.directory / "console.log", level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        keys_file = bundled_resource("offline_keys.json")
        keys = json.loads(keys_file.read_text(encoding="utf-8")) if keys_file.is_file() else {}
        manager = LicenceManager(store, keys, _device_id(store))
        models = bundled_resource("models")
        _runtime = LocalRuntime(store, manager, models)
        initial = application_directory() / "offline-entitlement.json"
        if initial.is_file() and not store.get("entitlement"):
            try:
                manager.install(json.loads(initial.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                store.audit("Initial entitlement could not be activated; import a valid renewal in the local console")
        check = verify_assets(models)
        if not check["ready"]:
            _runtime.error = "; ".join(check["errors"])
        assets = bundled_resource("offline-ui")
        app = create_app(store, manager, _runtime, assets)
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None, access_log=False, ws="none"))
        with _lock:
            _server = server
            _url = f"http://127.0.0.1:{port}"
        def open_ready():
            for _ in range(100):
                if server.started:
                    webbrowser.open(_url)
                    return
                if server.should_exit:
                    return
                time.sleep(0.1)
        threading.Thread(target=open_ready, daemon=True).start()
        server.run(sockets=[listener])
    except Exception as exc:
        logging.getLogger(__name__).exception("Local site console failed")
        _last_error = f"Offline console failed: {type(exc).__name__}"
    finally:
        if _runtime:
            _runtime.close()
        if listener:
            listener.close()
        with _lock:
            _server = None
            _url = ""


def start_agent() -> None:
    global _thread, _last_error
    with _lock:
        if _thread and _thread.is_alive():
            return
        from . import configure_offline_environment

        configure_offline_environment()
        _last_error = ""
        _thread = threading.Thread(target=_run, daemon=True, name="local-site-console")
        _thread.start()


def stop_agent() -> None:
    with _lock:
        server = _server
    if server:
        server.should_exit = True
    thread = _thread
    if thread and thread is not threading.current_thread():
        thread.join(timeout=15)


def get_runtime_status() -> dict:
    runtime = _runtime.status() if _runtime else {}
    return {"state": "Startup failed" if _last_error else "Offline console ready" if _server and _server.started else "starting", "message": _last_error or "Offline Site Console (development build)", "backend_url": _url, "model": str(runtime.get("detector", {}).get("active_model", "Monitoring not started")), "cameras": [{"id": item["id"], "name": item["name"], "status": "Video connected" if item["connected"] else "No connected video", "fps": item["fps"]} for item in runtime.get("cameras", [])]}


def start_monitoring() -> None:
    if not _runtime:
        raise RuntimeError("The local console is still starting")
    _runtime.start()


def stop_monitoring() -> None:
    if _runtime:
        _runtime.stop()


def get_agent_status() -> dict:
    return get_runtime_status()


def main(background_tray=False, on_open=lambda: None, on_quit=lambda: None):
    start_agent()
    for _ in range(200):
        if _url or _last_error:
            break
        time.sleep(0.1)
    if _last_error or not _url:
        raise RuntimeError(_last_error or "The local console did not start")
    from ..tray_icon import VantagTrayIcon

    def quit_local():
        stop_agent()
        on_quit()

    tray = VantagTrayIcon(start_monitoring, stop_monitoring, lambda: webbrowser.open(_url), quit_local, dashboard_url=_url, on_open=on_open)
    if background_tray:
        threading.Thread(target=tray.run, daemon=True, name="local-tray").start()
    else:
        tray.run()


def current_backend_url() -> str:
    return _url
