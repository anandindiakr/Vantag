import json
import os
import sys
import traceback
from pathlib import Path


def smoke_test(output_path: str) -> int:
    result = {"ok": False}
    try:
        os.environ["YOLO_AUTOINSTALL"] = "false"
        import cv2
        import mediapipe
        import numpy as np
        import onnxruntime
        import paho.mqtt.client
        import pystray
        import requests
        import torch
        import ultralytics
        from agent import __version__
        from agent.hand_landmarks import HandLandmarkDetector
        from agent.inference import ProductCountDetector, YoloInference, YoloPoseInference
        from agent.main import main

        frame = np.zeros((640, 640, 3), dtype=np.uint8)
        detector = YoloInference()
        if not detector.status.get("is_preferred") or detector.status.get("onnx_output_shape") != [1, 300, 6]:
            raise RuntimeError(f"YOLO26 unavailable: {detector.status}")
        detector.detect(frame)
        if detector.status.get("inference_count") != 1 or detector.status.get("last_inference_ms", -1) < 0:
            raise RuntimeError(f"YOLO26 inference failed or reported invalid timing: {detector.status}")
        pose = YoloPoseInference()
        if pose._session is None:
            raise RuntimeError("Pose model failed to load")
        pose.detect_poses(frame)
        hands = HandLandmarkDetector()
        hands.detect(frame)
        if not hands.available:
            raise RuntimeError("Hand landmark model failed to load")
        products = ProductCountDetector()
        if products.count_products(frame) is None:
            raise RuntimeError(f"Product counter unavailable: {products.status}")
        result.update({
            "ok": True,
            "version": __version__,
            "frozen": bool(getattr(sys, "frozen", False)),
            "python": sys.version.split()[0],
            "model_status": detector.status,
            "pose_loaded": True,
            "hands_loaded": True,
            "product_status": products.status,
        })
    except Exception:
        result["error"] = traceback.format_exc()
    Path(output_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1

def offline_smoke_test(output_path: str) -> int:
    import base64
    import re
    import tempfile
    import time
    import webbrowser
    from agent.local import configure_offline_environment

    configure_offline_environment()
    blocked = []

    def network_guard(event, arguments):
        if event == "socket.connect":
            address = arguments[1]
            if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
                blocked.append(str(address[0]))
                raise RuntimeError("Offline package test blocked a non-loopback connection")
        elif event == "socket.getaddrinfo" and arguments[0] not in {"localhost", "127.0.0.1", "::1", None}:
            blocked.append(str(arguments[0]))
            raise RuntimeError("Offline package test blocked an external DNS lookup")

    sys.addaudithook(network_guard)
    if smoke_test(output_path) != 0:
        return 1
    result = json.loads(Path(output_path).read_text(encoding="utf-8"))
    result["ok"] = False
    original_home = os.environ.get("USERPROFILE")
    original_open = webbrowser.open
    desktop = None
    try:
        import requests
        from agent.local import desktop

        with tempfile.TemporaryDirectory(prefix="vantag-offline-console-test-") as temporary:
            os.environ["USERPROFILE"] = temporary
            webbrowser.open = lambda *args, **kwargs: True
            desktop.start_agent()
            try:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    state = desktop.get_runtime_status()
                    if state["state"] == "Startup failed":
                        raise RuntimeError(state["message"])
                    if state["state"] == "Offline console ready":
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Packaged offline console startup timed out")
                url = desktop.current_backend_url()
                with requests.Session() as client:
                    client.trust_env = False

                    def request(method, path, expected=200, **kwargs):
                        response = client.request(method, url + path, timeout=15, **kwargs)
                        if response.status_code != expected:
                            raise RuntimeError(f"Offline console {path}: expected {expected}, got {response.status_code}")
                        return response

                    page = request("GET", "/").text
                    for asset in re.findall(r'(?:src|href)="([^"]+)"', page):
                        if not asset.startswith("/assets/"):
                            raise RuntimeError("Offline console contains an unexpected asset URL")
                        request("GET", asset)
                    request("GET", "/api/status", 401)
                    request('GET', '/api/people/staff', 401)
                    request("POST", "/api/setup", json={"username": "package-test", "password": "isolated-package-test-password"})
                    result['face_models'] = desktop._runtime.people.faces.initialize()
                    request('GET', '/api/people/settings')
                    request('GET', '/api/people/observations')
                    request('GET', '/api/people/staff')
                    request('POST', '/api/people/settings', 400, json={'capture_enabled': True, 'authorised': True})
                    request('GET', '/api/incidents')
                    request("POST", "/api/site", json={"name": "Isolated package test", "timezone": "Asia/Jakarta"})
                    request("POST", "/api/cameras", 403, json={"name": "Unlicensed test"})
                    request("GET", "/api/frame/test", 403)
                    store = desktop._runtime.store
                    if store.directory != Path(temporary) / ".vantag" / "offline-site":
                        raise RuntimeError("Packaged test did not isolate the site directory")
                    store.record_count("package-test", "2026-11-16", 1, 2, "test-run")
                    store.record_event({"event_id": "package-test", "snapshot_b64": base64.b64encode(b"package-test-evidence").decode()})
                    events = request("GET", "/api/events").json()
                    evidence = request("GET", events[0]["evidence"]["snapshot_b64"]).content
                    if evidence != b"package-test-evidence":
                        raise RuntimeError("Packaged evidence did not round-trip")
                    if request("GET", "/api/counts?day=2026-11-16").json()[0]["entries"] != 2:
                        raise RuntimeError("Packaged count persistence did not round-trip")
                    request("GET", "/api/counts.csv?day=2026-11-16")
                    request("GET", "/api/backup")
                    request("GET", "/api/status", 403, headers={"Origin": "https://example.com"})
                    result["offline_console"] = "Loopback startup, bundled assets, owner login, timezone, licence restrictions, counts, evidence, CSV and backup passed"
            finally:
                desktop.stop_agent()
        if blocked:
            raise RuntimeError("Offline package attempted non-loopback networking")
        result.update(ok=True, blocked_network_attempts=blocked, qualification="Development-host smoke test with Python socket guard, not clean-PC or firewall qualification")
    except Exception:
        result["error"] = traceback.format_exc()
        result["blocked_network_attempts"] = blocked
    finally:
        webbrowser.open = original_open
        if original_home is None:
            os.environ.pop("USERPROFILE", None)
        else:
            os.environ["USERPROFILE"] = original_home
    Path(output_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


def ui_smoke_test(output_path: str) -> int:
    import subprocess
    import threading
    from agent.single_instance import SingleInstance
    from agent.status_window import AgentStatusWindow
    from agent.tray_icon import VantagTrayIcon

    result = {"ok": False}
    instance = SingleInstance("Local\\VantagAgentPackageTest")
    if not instance.acquire():
        raise RuntimeError("Could not acquire the package-test instance lock")
    threading.Thread(target=instance.listen_for_show_requests, daemon=True).start()
    window = AgentStatusWindow(status_provider=lambda: {
        "state": "running",
        "backend_url": "https://example.com",
        "model": "YOLO26 active",
        "cameras": [{"id": "test-camera", "name": "Test camera", "status": "Connected", "fps": 5.0}],
    })
    tray = VantagTrayIcon(lambda: None, lambda: None, lambda: None, lambda: None, on_open=window.show)
    threading.Thread(target=tray.run, daemon=True, name="package-test-tray").start()

    def poll_show_requests():
        if instance.requested.is_set():
            instance.requested.clear()
            window._show_now()
        if not window._closed:
            window.root.after(100, poll_show_requests)

    def verify_relaunch():
        try:
            window.hide()
            command = [sys.executable, "--ui-test-show"] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).resolve()), "--ui-test-show"]
            child = subprocess.run(command, timeout=15, check=False)
            result["second_launch_exit_code"] = child.returncode
        except Exception:
            result["error"] = traceback.format_exc()

    def verify():
        try:
            window.refresh()
            result.update({
                "ok": bool(window.root.winfo_viewable()) and result.get("second_launch_exit_code") == 0 and bool(tray._icon and tray._icon.visible),
                "title": window.root.title(),
                "model": window.model_label.cget("text"),
                "cameras": list(window.camera_list.get_children()),
                "tray_visible": bool(tray._icon and tray._icon.visible),
            })
            window._closed = True
            if tray._icon:
                tray._icon.stop()
            window.root.destroy()
        except Exception:
            result["error"] = traceback.format_exc()
            window._closed = True
            window.root.destroy()

    poll_show_requests()
    window.root.after(1500, verify_relaunch)
    window.root.after(3500, verify)
    try:
        window.run()
    finally:
        instance.release()
    Path(output_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


def local_mode_requested(arguments=None, directory=None) -> bool:
    arguments = sys.argv[1:] if arguments is None else arguments
    if "--offline" in arguments:
        return True
    if directory is None:
        from agent.resources import application_directory

        directory = application_directory()
    try:
        return json.loads((Path(directory) / "config.json").read_text(encoding="utf-8")).get("mode") == "offline"
    except (OSError, ValueError, AttributeError):
        return False


def runtime_module():
    import importlib

    if local_mode_requested():
        from agent.local import configure_offline_environment

        configure_offline_environment()
        return importlib.import_module("agent.local.desktop")
    return importlib.import_module("agent.main")


def run_desktop() -> int:
    import threading
    from agent.single_instance import SingleInstance, show_existing_window
    from agent.status_window import AgentStatusWindow

    instance = SingleInstance()
    if not instance.acquire():
        show_existing_window()
        return 0

    def background(action):
        def run():
            try:
                action()
            except Exception as exc:
                message = str(exc)
                window.root.after(0, lambda: window.state_label.configure(text=f"Action failed: {message}"))
        threading.Thread(target=run, daemon=True).start()

    def bootstrap():
        try:
            agent_main = runtime_module()

            window.set_status_provider(agent_main.get_agent_status)
            agent_main.main(
                background_tray=True,
                on_open=window.show,
                on_quit=lambda: window.root.after(0, window.quit),
            )
        except Exception as exc:
            traceback.print_exc()
            window.set_status_provider(lambda: {
                "state": "Startup failed",
                "message": str(exc),
                "backend_url": "The agent could not start. Check the error above.",
                "model": "Not started",
                "cameras": [],
            })

    def agent_main_start():
        runtime_module().start_monitoring()

    def agent_main_stop():
        runtime_module().stop_monitoring()

    def current_backend_url():
        module = runtime_module()
        if local_mode_requested():
            return module.current_backend_url() or "about:blank"
        return getattr(module._config, "backend_url", None) or "https://retail-vantag.com"

    window = AgentStatusWindow(
        on_start=lambda: background(agent_main_start),
        on_stop=lambda: background(agent_main_stop),
        on_open=lambda: __import__("webbrowser").open(current_backend_url()),
        on_quit=lambda: background(agent_main_stop),
    )
    threading.Thread(target=bootstrap, daemon=True, name="agent-bootstrap").start()
    threading.Thread(target=instance.listen_for_show_requests, daemon=True, name="agent-show-requests").start()

    def poll_show_requests():
        if instance.requested.is_set():
            instance.requested.clear()
            window._show_now()
        if not window._closed:
            window.root.after(250, poll_show_requests)

    poll_show_requests()
    window.run()
    if local_mode_requested():
        runtime_module().stop_agent()
    instance.release()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--ui-test-show":
        from agent.single_instance import show_existing_window

        show_existing_window(name="Local\\VantagAgentPackageTest")
        sys.exit(0)
    if len(sys.argv) == 3 and sys.argv[1] == "--offline-smoke-test":
        sys.exit(offline_smoke_test(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        sys.exit(smoke_test(sys.argv[2]))
    if len(sys.argv) == 3 and sys.argv[1] == "--ui-test":
        sys.exit(ui_smoke_test(sys.argv[2]))
    try:
        if getattr(sys, "frozen", False) and not (Path(sys.executable).parent / "config.json").is_file():
            raise FileNotFoundError("config.json is missing. Extract all files and download a fresh agent from your account if necessary.")
        sys.exit(run_desktop())
    except Exception as exc:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, f"Vantag Agent could not start: {exc}", "Vantag Agent", 0x10)
        raise
