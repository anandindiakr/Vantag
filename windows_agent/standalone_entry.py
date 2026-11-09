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
            from agent import main as agent_main

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
        from agent.main import start_monitoring
        start_monitoring()

    def agent_main_stop():
        from agent.main import stop_monitoring
        stop_monitoring()

    def current_backend_url():
        from agent.main import _config
        return getattr(_config, "backend_url", None) or "https://retail-vantag.com"

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
    instance.release()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--ui-test-show":
        from agent.single_instance import show_existing_window

        show_existing_window(name="Local\\VantagAgentPackageTest")
        sys.exit(0)
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
