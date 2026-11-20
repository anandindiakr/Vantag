from __future__ import annotations

import base64
import re
import threading
import time
import uuid
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .policy import CORE_FEATURES, feature_enabled


class LocalSink:
    def __init__(self, store, permitted=lambda: True, event_permitted=lambda event: True):
        self.store = store
        self.permitted = permitted
        self.event_permitted = event_permitted
        self.enabled = True
        self.error = ""
        self.frames = {}
        self.lock = threading.Lock()

    def post_event(self, event: dict) -> bool:
        if not self.enabled or not self.permitted() or not self.event_permitted(event):
            return False
        try:
            self.store.record_event(event)
        except (ValueError, OSError) as exc:
            self.error = f"Evidence could not be saved: {type(exc).__name__}. Check local storage."
            return False
        self.error = ""
        return True

    def post_count_snapshot(self, camera_id: str, count: int, snapshot_b64: str) -> bool:
        return self.post_event({"camera_id": camera_id, "event_type": "count_evidence", "people_visible": count, "snapshot_b64": snapshot_b64})

    def push_frame(self, camera_id: str, frame_b64: str) -> bool:
        if not self.enabled or not self.permitted():
            return False
        raw = base64.b64decode(frame_b64, validate=True)
        if len(raw) > 4 * 1024 * 1024:
            return False
        with self.lock:
            self.frames[camera_id] = (raw, time.time())
        return True

    def frame(self, camera_id: str):
        with self.lock:
            frame = self.frames.get(camera_id)
            return frame if frame and time.time() - frame[1] < 10 else None


class LocalRuntime:
    def __init__(self, store, licence, model_dir: Path):
        self.store = store
        self.licence = licence
        self.model_dir = model_dir
        self.sink = LocalSink(store, self.permitted, self.event_permitted)
        self.workers = []
        self.detector = None
        self.pose = None
        self.products = None
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.error = ""
        self.calibration = {}
        threading.Thread(target=self._supervise, daemon=True, name="local-supervisor").start()

    def permitted(self) -> bool:
        return self.licence.status().can_process

    def event_permitted(self, event: dict) -> bool:
        camera = next((item for item in self.store.cameras() if item["id"] == event.get("camera_id")), None)
        if camera is None:
            return False
        feature = "people_count" if event.get("event_type") == "count_evidence" else event.get("event_type", "")
        claims = self.licence.status().claims
        return feature_enabled(camera, feature, claims, self.store.get("site", {}).get("timezone", "UTC"))

    def start(self) -> None:
        try:
            self._start()
        except Exception as exc:
            self.error = f"Monitoring could not start: {exc}"
            raise

    def _start(self) -> None:
        with self.lock:
            from .storage import require_capacity
            require_capacity(self.store)
            status = self.licence.status()
            if not status.can_process:
                raise ValueError("A valid offline entitlement is required")
            cameras = [camera for camera in self.store.cameras(include_secrets=True) if camera.get("enabled", True)]
            if len(cameras) > status.claims["camera_limit"]:
                raise ValueError("Camera limit for concurrent monitoring exceeded; saved configurations are retained. Disable excess cameras or import a larger signed entitlement. Existing streams were not stopped.")
            self._stop_workers()
            self.sink = LocalSink(self.store, self.permitted, self.event_permitted)
            if not cameras:
                return
            from .detector import VerifiedDetector
            from ..inference import YoloInference, YoloPoseInference, ProductCountDetector
            from .hardware import calibrate_detector, verify_assets
            check = verify_assets(self.model_dir)
            if not check["ready"]:
                raise ValueError("; ".join(check["errors"]))
            self.detector, self.calibration = calibrate_detector(self.model_dir / "yolo26n.onnx", YoloInference)
            if self.detector is None:
                raise ValueError(self.calibration["error"])
            if not self.detector.status.get("is_preferred"):
                raise ValueError("The bundled detector is not verified native YOLO26")
            self.detector = VerifiedDetector(self.detector, lambda: YoloInference(model_path=str(self.model_dir / "yolo26n.onnx"), device="cpu"))
            pose_path = self.model_dir / "yolov8n-pose.onnx"
            self.pose = YoloPoseInference(model_path=str(pose_path), device=self.detector.device) if pose_path.is_file() else None
            self.products = ProductCountDetector(offline=True, model_dir=self.model_dir)
            fps = max(0.25, min(5.0, 600 / max(1, self.calibration["inference_ms"]) / len(cameras)))
            self.error = ""
            try:
                for camera in cameras:
                    worker = self._make_worker(camera, fps)
                    worker.start()
                    self.workers.append(worker)
            except Exception:
                self._stop_workers()
                raise

    def _make_worker(self, camera: dict, fps: float):
        from ..config import CameraConfig
        from .worker import LocalCameraWorker
        allowed = {item.name for item in fields(CameraConfig)}
        data = {key: value for key, value in camera.items() if key in allowed}
        claims = self.licence.status().claims
        detections = {name: bool(value and name in claims["features"]) for name, value in camera.get("detections", {}).items()}
        data["detections"] = detections or {name: False for name in CORE_FEATURES}

        def detection_policy():
            current = next((item for item in self.store.cameras() if item["id"] == camera["id"]), {})
            entitlement = self.licence.status()
            timezone_name = self.store.get("site", {}).get("timezone", "UTC")
            return {name: entitlement.can_process and feature_enabled(current, name, entitlement.claims, timezone_name) for name in CORE_FEATURES}

        parent_sink = self.sink
        sink = LocalSink(self.store, lambda: parent_sink.enabled and self.permitted(), self.event_permitted)
        sink.frames = parent_sink.frames
        sink.lock = parent_sink.lock
        worker = LocalCameraWorker(config=CameraConfig(**data), inference=self.detector, api_client=sink, target_fps=fps, pose_inference=self.pose, people_count_zones=data.get("people_count_zones", []), inventory_zones=data.get("inventory_zones", []), exclusion_zones=data.get("exclusion_zones", []), detections=data["detections"], product_count_detector=self.products, high_value_counter=data.get("high_value_counter", {}), count_day=lambda: datetime.now(ZoneInfo(self.store.get("site", {}).get("timezone", "UTC"))).strftime("%Y-%m-%d"), detection_policy=detection_policy)
        worker._local_run_id = str(uuid.uuid4())
        worker._local_sink = sink
        return worker

    def apply_camera(self, camera_id: str) -> bool:
        with self.lock:
            if not self.workers:
                return False
            replacement = None
            try:
                from .storage import require_capacity
                require_capacity(self.store)
                status = self.licence.status()
                if not status.can_process:
                    raise ValueError("A valid offline entitlement is required")
                cameras = self.store.cameras(include_secrets=True)
                enabled = [camera for camera in cameras if camera.get("enabled", True)]
                if len(enabled) > status.claims["camera_limit"]:
                    raise ValueError("Camera limit exceeded")
                camera = next((item for item in cameras if item["id"] == camera_id), None)
                if camera is None:
                    raise ValueError("Saved camera was not found")
                fps = max(0.25, min(5.0, 600 / max(1, self.calibration["inference_ms"]) / max(1, len(enabled))))
                if camera.get("enabled", True):
                    replacement = self._make_worker(camera, fps)
                self._persist_counts()
                for worker in list(self.workers):
                    if worker.config.id == camera_id:
                        worker._local_sink.enabled = False
                        worker.stop()
                        self.workers.remove(worker)
                with self.sink.lock:
                    self.sink.frames.pop(camera_id, None)
                if replacement:
                    replacement.start()
                    self.workers.append(replacement)
                for worker in self.workers:
                    worker._target_fps = fps
                self.error = ""
                return True
            except Exception as exc:
                if replacement:
                    replacement._local_sink.enabled = False
                    replacement.stop()
                self.error = f"Camera saved, but live application failed: {type(exc).__name__}. Retry Start / apply configuration."
                raise

    def remove_camera(self, camera_id: str) -> None:
        with self.lock:
            self._persist_counts()
            for worker in list(self.workers):
                if worker.config.id == camera_id:
                    worker._local_sink.enabled = False
                    worker.stop()
                    self.workers.remove(worker)
            with self.sink.lock:
                self.sink.frames.pop(camera_id, None)

    def frame_for_stream(self, url: str):
        with self.lock:
            for worker in self.workers:
                if worker.config.rtsp_url == url:
                    return self.sink.frame(worker.config.id)
        return None

    def _persist_counts(self) -> None:
        for worker in self.workers:
            sample = worker.count_sample
            if not sample or not self.event_permitted({"camera_id": worker.config.id, "event_type": "count_evidence"}):
                continue
            if sample["updated_at"] == getattr(worker, "_local_saved_sample", None):
                continue
            self.store.record_count(worker.config.id, sample["day"], int(sample["visible"]), int(sample["entries"]), worker._local_run_id, sample["updated_at"])
            worker._local_saved_sample = sample["updated_at"]

    def _stop_workers(self) -> None:
        try:
            self._persist_counts()
        except Exception as exc:
            self.error = f"Last count sample could not be saved: {type(exc).__name__}"
        self.sink.enabled = False
        for worker in self.workers:
            worker.stop()
        self.workers.clear()
        with self.sink.lock:
            self.sink.frames.clear()

    def stop(self) -> None:
        with self.lock:
            self._stop_workers()

    def close(self) -> None:
        self.stopping.set()
        self.stop()

    def _supervise(self) -> None:
        while not self.stopping.wait(1):
            try:
                with self.lock:
                    if not self.permitted():
                        if self.workers:
                            self._stop_workers()
                        continue
                    if self.workers and int(time.monotonic()) % 15 == 0:
                        from .storage import require_capacity
                        require_capacity(self.store)
                    self._persist_counts()
            except Exception as exc:
                self.error = f"Local monitoring supervision failed: {type(exc).__name__}"
                with self.lock:
                    self._stop_workers()

    def _analytic_status(self, worker, configuration, entitlement, timezone_name, feature):
        configured = bool(configuration.get("detections", {}).get(feature))
        effective = entitlement.can_process and feature_enabled(configuration, feature, entitlement.claims, timezone_name)
        analyzer = getattr(worker, "_analyzer", None)
        pose = getattr(analyzer, "_pose_detector", None)
        details = dict(getattr(pose, "status", {})) if feature == "shoplifting" else {}
        if not configured:
            state = "Off for this camera"
        elif not entitlement.can_process or feature not in entitlement.claims.get("features", []):
            state = "Blocked by entitlement"
        elif not effective:
            state = "Outside configured schedule or camera disabled"
        elif feature == "inventory_movement" and not configuration.get("inventory_zones"):
            state = "Draw and save a shelf zone first"
        elif not worker.is_connected:
            state = "Waiting for video"
        elif worker.inference_error:
            state = worker.inference_error
        elif feature == "shoplifting":
            if details.get("error"):
                state = details["error"] + "; proximity heuristic only"
            elif pose is None:
                state = "Pose model unavailable; proximity heuristic only"
            elif not details.get("evaluated_at") or time.time() - details["evaluated_at"] > 10:
                state = "Waiting for a recent concealment pose analysis"
            else:
                state = "Analysing suspected concealment; review required, not proof of theft"
        elif not worker.count_sample or time.time() - worker.count_sample["updated_at"] > 10:
            state = "Waiting for recent shelf analysis"
        else:
            state = "Analysing shelf appearance changes; not an exact item count"
            details["zones"] = {key: dict(value) for key, value in getattr(analyzer, "_inventory_diag", {}).copy().items()}
        return dict(details, state=state, configured=configured, effective=effective, requires_review=True)

    def status(self) -> dict:
        with self.lock:
            cameras = []
            saved = {camera["id"]: camera for camera in self.store.cameras()}
            entitlement = self.licence.status()
            timezone_name = self.store.get("site", {}).get("timezone", "UTC")
            for worker in self.workers:
                frame = self.sink.frame(worker.config.id)
                configuration = saved.get(worker.config.id, {})
                fall = getattr(getattr(worker, "_analyzer", None), "_fall_detector", None)
                fall_status = dict(getattr(fall, "status", {}))
                configured = bool(configuration.get("detections", {}).get("fall_detected"))
                effective = entitlement.can_process and feature_enabled(configuration, "fall_detected", entitlement.claims, timezone_name)
                if not configured:
                    fall_state = "Off for this camera"
                elif not entitlement.can_process or "fall_detected" not in entitlement.claims.get("features", []):
                    fall_state = "Blocked by entitlement"
                elif not effective:
                    fall_state = "Outside configured schedule or camera disabled"
                elif not worker.is_connected:
                    fall_state = "Waiting for video"
                elif fall_status.get("error"):
                    fall_state = fall_status["error"]
                elif not fall_status.get("evaluated_at") or time.time() - fall_status["evaluated_at"] > 10:
                    fall_state = "Waiting for a recent pose analysis"
                else:
                    fall_state = "Analysing pose; review candidates, not guaranteed fall detection"
                fall_status.update(state=fall_state, configured=configured, effective=effective)
                cameras.append({
                    "id": worker.config.id, "name": worker.config.name,
                    "connected": bool(worker.is_connected and frame), "fps": round(worker.current_fps, 1),
                    "connection_error": re.sub(r"rtsp://\S+", "[protected stream]", str(getattr(worker, "error_msg", "")))[:600] if not frame else "",
                    "connection_failures": getattr(worker, "consecutive_failures", 0),
                    "inference_ms": round(worker.inference_ms, 1), "inference_error": worker.inference_error,
                    "sample_at": worker.count_sample["updated_at"] if worker.count_sample else None,
                    "frame_age_sec": round(time.time() - frame[1], 1) if frame else None,
                    "fall_status": fall_status,
                    "theft_status": self._analytic_status(worker, configuration, entitlement, timezone_name, "shoplifting"),
                    "inventory_status": self._analytic_status(worker, configuration, entitlement, timezone_name, "inventory_movement"),
                })
            return {
                "running": bool(self.workers), "error": self.error or self.sink.error, "calibration": self.calibration,
                "detector": dict(self.detector.status) if self.detector else {}, "cameras": cameras,
                "camera_capacity": {"configured": len(saved), "enabled": sum(camera.get("enabled", True) for camera in saved.values()), "monitored": len(self.workers), "connected": sum(camera["connected"] for camera in cameras), "entitlement_limit": entitlement.claims.get("camera_limit", 0)},
                "advanced_features": {
                    "staff_matching": "unavailable: local model redistribution not qualified",
                    "visual_verification": "unavailable: no qualified local VLM bundled",
                    "visual_search": "unavailable: local embedding package not qualified",
                    "assistant": "unavailable: no qualified local assistant bundled",
                    "high_value_counter": "unavailable: local configuration and hand model qualification incomplete",
                },
            }
