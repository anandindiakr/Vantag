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


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        sys.exit(smoke_test(sys.argv[2]))
    try:
        if getattr(sys, "frozen", False) and not (Path(sys.executable).parent / "config.json").is_file():
            raise FileNotFoundError("config.json is missing. Extract all files and download a fresh agent from your account if necessary.")
        from agent.main import main

        main()
    except Exception as exc:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, f"Vantag Agent could not start: {exc}", "Vantag Agent", 0x10)
        raise
