import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_offline_product_counter_never_downloads_missing_weights(tmp_path, monkeypatch):
    import requests
    from agent.inference import ProductCountDetector
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: pytest.fail("Offline model attempted download"))
    detector = ProductCountDetector(offline=True, model_dir=tmp_path)
    detector._ensure_loaded()
    assert detector.status["state"] == "failed"
    assert "missing" in detector.status["error"].lower()


def test_calibration_retries_cpu_when_gpu_does_not_really_run(tmp_path, monkeypatch):
    from agent.local import hardware
    seen = []

    class Detector:
        def __init__(self, model_path, device):
            seen.append(device)
            self.device = device
            self.status = {"provider": "CUDAExecutionProvider" if device == "cuda" else "CPUExecutionProvider", "inference_count": 0, "is_preferred": True}

        def detect(self, frame):
            if self.device == "cuda":
                raise RuntimeError("GPU unavailable")
            self.status["inference_count"] += 1
            return []

    monkeypatch.setattr(hardware, "available_devices", lambda: ["cuda", "cpu"])
    detector, result = hardware.calibrate_detector(tmp_path / "model.onnx", Detector)
    assert seen == ["cuda", "cpu"]
    assert detector.device == "cpu"
    assert result["provider"] == "CPUExecutionProvider"
    assert result["fallback_reason"]


def test_missing_offline_model_is_not_reported_ready(tmp_path):
    from agent.local.hardware import verify_assets
    assert verify_assets(tmp_path)["ready"] is False


def test_manifest_checks_actual_file_hashes(tmp_path):
    import hashlib
    from agent.local.hardware import verify_assets
    for name in ["yolo26n.onnx", "yolov8n-pose.onnx", "yolov8s-worldv2.pt", "hand_landmarker.task"]:
        (tmp_path / name).write_bytes(b"test-asset")
    records = {name: hashlib.sha256(b"test-asset").hexdigest() for name in ["yolo26n.onnx", "yolov8n-pose.onnx", "yolov8s-worldv2.pt", "hand_landmarker.task"]}
    (tmp_path / "offline-manifest.json").write_text(json.dumps({"version": 1, "sha256": records}))
    assert verify_assets(tmp_path)["ready"] is True
    (tmp_path / "yolo26n.onnx").write_bytes(b"corrupted")
    assert verify_assets(tmp_path)["ready"] is False


def test_offline_mode_is_explicit_and_online_is_unchanged(tmp_path):
    from standalone_entry import local_mode_requested
    assert not local_mode_requested([], tmp_path)
    assert local_mode_requested(["--offline"], tmp_path)
    (tmp_path / "config.json").write_text('{"mode":"offline"}')
    assert local_mode_requested([], tmp_path)


def test_offline_policy_applies_before_runtime_import(monkeypatch):
    import importlib
    import os
    import standalone_entry

    monkeypatch.setattr(standalone_entry, "local_mode_requested", lambda: True)
    for name in ("YOLO_OFFLINE", "YOLO_AUTOINSTALL", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY", "DO_NOT_TRACK"):
        monkeypatch.setenv(name, "unset")

    def load(name):
        assert name == "agent.local.desktop"
        assert os.environ["YOLO_OFFLINE"] == "1"
        assert os.environ["YOLO_AUTOINSTALL"] == "false"
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
        assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"
        assert os.environ["DO_NOT_TRACK"] == "1"
        return "offline-runtime"

    monkeypatch.setattr(importlib, "import_module", load)
    assert standalone_entry.runtime_module() == "offline-runtime"


def test_online_launch_does_not_change_offline_environment(monkeypatch):
    import importlib
    import os
    import standalone_entry

    monkeypatch.setattr(standalone_entry, "local_mode_requested", lambda: False)
    monkeypatch.setenv("YOLO_OFFLINE", "existing-value")
    monkeypatch.setattr(importlib, "import_module", lambda name: name)
    assert standalone_entry.runtime_module() == "agent.main"
    assert os.environ["YOLO_OFFLINE"] == "existing-value"
