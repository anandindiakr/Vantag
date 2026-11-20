from __future__ import annotations

from ..camera_worker import CameraWorker


class LocalCameraWorker(CameraWorker):
    def __init__(self, *args, detection_policy, **kwargs):
        super().__init__(*args, **kwargs)
        self._detection_policy = detection_policy
        from .fall import PoseFallDetector
        self._analyzer._fall_detector = PoseFallDetector(self.config.id, kwargs.get("pose_inference"), excluded=lambda box, frame: self._analyzer._in_exclusion_zone(box, frame.shape[1], frame.shape[0]))

    def _run_inference(self, frame):
        try:
            self._analyzer._detections = self._detection_policy()
            if not self._analyzer._detections.get("fall_detected"):
                self._analyzer._fall_detector.reset()
            if not any(self._analyzer._detections.values()):
                return
            super()._run_inference(frame)
        except Exception as exc:
            self.inference_error = f"Local policy failed: {type(exc).__name__}"
        finally:
            self._infer_inflight.clear()
