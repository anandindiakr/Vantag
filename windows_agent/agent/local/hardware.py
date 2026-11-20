from __future__ import annotations

import hashlib
import json
import statistics
import time
from pathlib import Path

CORE_ASSETS = ("yolo26n.onnx", "yolov8n-pose.onnx", "yolov8s-worldv2.pt", "hand_landmarker.task")


def verify_assets(directory: Path) -> dict:
    errors = []
    try:
        manifest = json.loads((directory / "offline-manifest.json").read_text(encoding="utf-8"))
        if manifest["version"] != 1:
            raise ValueError("Unsupported offline model manifest")
        for name in CORE_ASSETS:
            path = directory / name
            if not path.is_file():
                errors.append(f"Missing {name}")
                continue
            with path.open("rb") as source:
                digest = hashlib.file_digest(source, "sha256").hexdigest()
            if digest != manifest["sha256"].get(name):
                errors.append(f"Integrity check failed: {name}")
    except (OSError, ValueError, KeyError, TypeError):
        errors.append("A valid offline model manifest is required")
    return {"ready": not errors, "errors": errors}


def available_devices() -> list[str]:
    import onnxruntime as ort
    providers = ort.get_available_providers()
    devices = []
    if "CUDAExecutionProvider" in providers:
        devices.append("cuda")
    if "DmlExecutionProvider" in providers:
        devices.append("dml")
    return devices + ["cpu"]


def calibrate_detector(model_path: Path, factory) -> tuple:
    import numpy as np
    failures = []
    for device in available_devices():
        try:
            detector = factory(model_path=str(model_path), device=device)
            if detector.status.get("error"):
                raise RuntimeError(detector.status["error"])
            frame = np.zeros((640, 640, 3), dtype=np.uint8)
            timings = []
            initial = detector.status.get("inference_count", 0)
            for _ in range(3):
                started = time.perf_counter()
                detector.detect(frame)
                timings.append((time.perf_counter() - started) * 1000)
            if detector.status.get("inference_count", 0) < initial + 3:
                raise RuntimeError("Model did not complete three inference calls")
            actual = detector.status.get("provider")
            expected = {"cuda": "CUDAExecutionProvider", "dml": "DmlExecutionProvider", "cpu": "CPUExecutionProvider"}[device]
            if actual != expected:
                raise RuntimeError("Requested acceleration provider did not activate")
            return detector, {"provider": actual, "inference_ms": round(statistics.median(timings), 2), "fallback_reason": "; ".join(failures), "scope": "Synthetic-frame detector calibration only; pose/product workload and field camera capacity are not validated"}
        except Exception as exc:
            failures.append(f"{device}: {type(exc).__name__}")
    return None, {"error": "No working inference provider: " + "; ".join(failures)}
