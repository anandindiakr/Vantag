from __future__ import annotations

import threading


class VerifiedDetector:
    def __init__(self, detector, cpu_factory):
        self._detector = detector
        self._cpu_factory = cpu_factory
        self._lock = threading.RLock()
        self._error = ""
        self._fallback = ""

    @property
    def device(self):
        return self._detector.device

    @property
    def status(self) -> dict:
        return dict(self._detector.status, runtime_error=self._error, runtime_fallback=self._fallback)

    def _detect(self, frame, conf_threshold):
        before = self._detector.status.get("inference_count", 0)
        result = self._detector.detect(frame, conf_threshold=conf_threshold)
        if self._detector.status.get("inference_count", 0) != before + 1:
            raise RuntimeError("Detector did not complete inference; this sample is not a measured zero")
        return result

    def detect(self, frame, conf_threshold=0.5):
        with self._lock:
            try:
                result = self._detect(frame, conf_threshold)
                self._error = ""
                return result
            except Exception as exc:
                self._error = f"Detector failed: {type(exc).__name__}"
                if self.device == "cpu":
                    raise
                self._detector = self._cpu_factory()
                if not self._detector.status.get("is_preferred"):
                    raise RuntimeError("CPU fallback is not verified native YOLO26") from exc
                result = self._detect(frame, conf_threshold)
                self._fallback = "GPU inference failed; CPU fallback completed real inference. Reassess camera capacity."
                self._error = ""
                return result
