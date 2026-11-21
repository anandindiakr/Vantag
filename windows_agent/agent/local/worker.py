from __future__ import annotations

from ..camera_worker import CameraWorker


class LocalCameraWorker(CameraWorker):
    def __init__(self, *args, detection_policy, person_quality=None, people_observer=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._detection_policy = detection_policy
        self._people_observer = people_observer
        from .person_quality import PersonQuality
        self._analyzer._person_quality = PersonQuality(kwargs.get('pose_inference'), {'mode': 'balanced', **(person_quality or {})})
        self._analyzer._tracker.min_hits = self._analyzer._person_quality.confirmation_frames
        self._analyzer._tracker.high_conf_threshold = self._analyzer._person_quality.confidence
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
            if self._people_observer and not self.inference_error:
                self._people_observer.submit(self.config.id, self._local_run_id, getattr(self._analyzer, 'last_person_boxes', []), frame, lambda: self._local_sink.enabled and self._detection_policy().get('people_count', False))
        except Exception as exc:
            self.inference_error = f"Local policy failed: {type(exc).__name__}"
        finally:
            self._infer_inflight.clear()
