"""
tests/backend/test_ingestion.py
================================
pytest test suite for the Vantag ingestion layer and tamper detector.

Covers:
  * CameraRegistry.load() with a mock YAML payload
  * StreamManager frame-buffer overflow (oldest-frame-drop policy)
  * TamperDetector BLOCKED detection with a solid-black frame
"""

from __future__ import annotations

import queue
import time
import textwrap
from io import StringIO
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Path setup – ensure the backend package is importable when tests are run
# from the repo root.
# ---------------------------------------------------------------------------
import sys
import os

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent / "backend"
if str(_BACKEND_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_black_frame(height: int = 480, width: int = 640) -> np.ndarray:
    """Return a fully black BGR frame (all zeros)."""
    return np.zeros((height, width, 3), dtype=np.uint8)


def _make_noisy_frame(height: int = 480, width: int = 640) -> np.ndarray:
    """Return a frame with random noise (non-trivial variance)."""
    rng = np.random.default_rng(seed=42)
    return rng.integers(0, 256, (height, width, 3), dtype=np.uint8)


# ============================================================
# TEST GROUP 1: CameraRegistry
# ============================================================

MOCK_YAML = textwrap.dedent("""\
    global:
      mqtt_broker: "localhost"
      mqtt_port: 1883
      reconnect_backoff_max: 64
      frame_buffer_size: 30
      risk_score_window_seconds: 60

    cameras:
      - id: "test-cam-01"
        name: "Test Camera 1"
        rtsp_url: "rtsp://admin:pass@10.0.0.1:554/stream"
        location: "Test Floor"
        resolution:
          width: 1280
          height: 720
        fps_target: 25
        enabled: true
        low_light_mode: false
        zones:
          - name: "zone_a"
            points:
              - [0, 0]
              - [640, 0]
              - [640, 720]
              - [0, 720]
        staff_zone_colors:
          - "#FF0000"

      - id: "test-cam-02"
        name: "Test Camera 2"
        rtsp_url: "rtsp://admin:pass@10.0.0.2:554/stream"
        location: "Test Floor – Annex"
        resolution:
          width: 640
          height: 480
        fps_target: 15
        enabled: false
        low_light_mode: true
        zones: []
        staff_zone_colors: []
""")


class TestCameraRegistry:
    """Tests for CameraRegistry.load() and accessor methods."""

    def _make_registry(self, yaml_text: str = MOCK_YAML):
        """
        Build a CameraRegistry backed by a mocked YAML file so no real file
        system I/O is required.
        """
        from backend.ingestion.camera_registry import CameraRegistry

        registry = CameraRegistry(config_path="/fake/cameras.yaml")

        # Patch Path.exists → True and Path.open → StringIO with mock YAML.
        with (
            patch("backend.ingestion.camera_registry.Path.exists", return_value=True),
            patch(
                "backend.ingestion.camera_registry.Path.open",
                return_value=StringIO(yaml_text),
            ),
        ):
            registry.load()

        return registry

    # ------------------------------------------------------------------

    def test_load_returns_correct_camera_count(self):
        """load() should populate exactly 2 cameras from the mock YAML."""
        registry = self._make_registry()
        assert len(registry.all_cameras()) == 2

    def test_get_camera_by_id(self):
        """get_camera() should return the correct CameraConfig by id."""
        registry = self._make_registry()
        cam = registry.get_camera("test-cam-01")
        assert cam.id == "test-cam-01"
        assert cam.name == "Test Camera 1"
        assert cam.fps_target == 25
        assert cam.resolution.width == 1280
        assert cam.resolution.height == 720

    def test_camera_disabled_flag(self):
        """Camera 02 is disabled in the YAML; the flag must be preserved."""
        registry = self._make_registry()
        cam2 = registry.get_camera("test-cam-02")
        assert cam2.enabled is False

    def test_zones_parsed_correctly(self):
        """Zone points for cam-01 should be parsed into the right tuples."""
        registry = self._make_registry()
        zones = registry.get_zones("test-cam-01")
        assert len(zones) == 1
        assert zones[0].name == "zone_a"
        assert len(zones[0].points) == 4
        assert zones[0].points[0] == (0, 0)

    def test_get_camera_unknown_id_raises(self):
        """Accessing a non-existent camera id must raise KeyError."""
        registry = self._make_registry()
        with pytest.raises(KeyError):
            registry.get_camera("does-not-exist")

    def test_load_missing_global_field_raises_config_error(self):
        """YAML missing a required global field must raise ConfigError."""
        from backend.ingestion.camera_registry import ConfigError

        broken_yaml = textwrap.dedent("""\
            global:
              mqtt_broker: "localhost"
              # mqtt_port intentionally omitted
              reconnect_backoff_max: 64
              frame_buffer_size: 30
              risk_score_window_seconds: 60
            cameras: []
        """)
        registry_cls = __import__(
            "backend.ingestion.camera_registry", fromlist=["CameraRegistry"]
        ).CameraRegistry
        registry = registry_cls(config_path="/fake/cameras.yaml")

        with (
            patch("backend.ingestion.camera_registry.Path.exists", return_value=True),
            patch(
                "backend.ingestion.camera_registry.Path.open",
                return_value=StringIO(broken_yaml),
            ),
            pytest.raises(ConfigError),
        ):
            registry.load()

    def test_load_missing_camera_field_raises_config_error(self):
        """Camera entry missing 'rtsp_url' must raise ConfigError."""
        from backend.ingestion.camera_registry import ConfigError, CameraRegistry

        broken_yaml = textwrap.dedent("""\
            global:
              mqtt_broker: "localhost"
              mqtt_port: 1883
              reconnect_backoff_max: 64
              frame_buffer_size: 30
              risk_score_window_seconds: 60
            cameras:
              - id: "bad-cam"
                name: "Missing URL"
                location: "Nowhere"
                resolution:
                  width: 640
                  height: 480
                fps_target: 15
                enabled: true
                low_light_mode: false
                zones: []
                staff_zone_colors: []
                # rtsp_url intentionally omitted
        """)
        registry = CameraRegistry(config_path="/fake/cameras.yaml")
        with (
            patch("backend.ingestion.camera_registry.Path.exists", return_value=True),
            patch(
                "backend.ingestion.camera_registry.Path.open",
                return_value=StringIO(broken_yaml),
            ),
            pytest.raises(ConfigError),
        ):
            registry.load()

    def test_global_settings_accessible(self):
        """get_global() must expose the full global block."""
        registry = self._make_registry()
        g = registry.get_global()
        assert g["mqtt_broker"] == "localhost"
        assert g["mqtt_port"] == 1883
        assert g["frame_buffer_size"] == 30

    def test_load_not_called_raises_config_error(self):
        """Calling all_cameras() before load() must raise ConfigError."""
        from backend.ingestion.camera_registry import CameraRegistry, ConfigError
        registry = CameraRegistry(config_path="/fake/cameras.yaml")
        with pytest.raises(ConfigError, match="load\\(\\)"):
            registry.all_cameras()


# ============================================================
# TEST GROUP 2: StreamManager frame buffer overflow
# ============================================================

class TestStreamManagerFrameBuffer:
    """
    Tests for the _CameraWorker._push_frame bounded-queue / drop-oldest
    logic in isolation (no real RTSP streams required).
    """

    def _make_worker(self, buffer_size: int = 3):
        """Instantiate a _CameraWorker with a tiny buffer for testing."""
        from backend.ingestion.camera_registry import CameraConfig, Resolution
        from backend.ingestion.stream_manager import _CameraWorker

        cam = CameraConfig(
            id="buf-test-cam",
            name="Buffer Test",
            rtsp_url="rtsp://fake",
            location="Lab",
            resolution=Resolution(width=640, height=480),
            fps_target=25,
            enabled=True,
            low_light_mode=False,
            zones=[],
            staff_zone_colors=[],
        )
        return _CameraWorker(
            config=cam,
            buffer_size=buffer_size,
            reconnect_backoff_max=64,
        )

    def test_overflow_drops_oldest_frame(self):
        """
        When more frames than buffer_size are pushed, the oldest frame is
        dropped and only the most recent ones are retained.
        """
        worker = self._make_worker(buffer_size=3)

        # Push 5 frames labelled by a unique mean value (0, 10, 20, 30, 40).
        frames = [np.full((4, 4, 3), fill_value=i * 10, dtype=np.uint8) for i in range(5)]
        for f in frames:
            worker._push_frame(f)

        # Queue should have exactly 3 frames.
        assert worker._frame_queue.qsize() == 3

        # The OLDEST frame in the queue is now frame[2] (value=20).
        retrieved = []
        while True:
            f = worker.get_frame()
            if f is None:
                break
            retrieved.append(int(np.mean(f)))

        # We expect exactly 3 frames: values 20, 30, 40 (frames 0 and 1 dropped).
        assert len(retrieved) == 3
        assert retrieved == [20, 30, 40]

    def test_empty_queue_returns_none(self):
        """get_frame() on an empty queue should return None without blocking."""
        worker = self._make_worker(buffer_size=5)
        assert worker.get_frame() is None

    def test_exact_capacity_no_drop(self):
        """Pushing exactly buffer_size frames should not drop any."""
        worker = self._make_worker(buffer_size=4)
        frames = [np.zeros((4, 4, 3), dtype=np.uint8) for _ in range(4)]
        for f in frames:
            worker._push_frame(f)
        assert worker._frame_queue.qsize() == 4

    def test_one_over_capacity_drops_one(self):
        """Pushing buffer_size + 1 frames drops exactly one (the oldest)."""
        worker = self._make_worker(buffer_size=4)
        frames = [np.full((2, 2, 3), i, dtype=np.uint8) for i in range(5)]
        for f in frames:
            worker._push_frame(f)
        assert worker._frame_queue.qsize() == 4
        # Oldest remaining should have mean == 1 (frame 0 was dropped).
        first = worker.get_frame()
        assert int(np.mean(first)) == 1


# ============================================================
# TEST GROUP 3: TamperDetector – BLOCKED detection
# ============================================================

class TestTamperDetectorBlocked:
    """Tests for the BLOCKED tamper condition."""

    def _make_detector(self, blocked_duration: float = 0.05):
        """
        Create a TamperDetector with a very short blocked_duration so tests
        don't need to sleep for multiple seconds.
        """
        from backend.analyzers.tamper_detector import TamperDetector
        return TamperDetector(
            camera_id="test-cam",
            config={
                "blocked_brightness_threshold": 10.0,
                "blocked_duration_seconds": blocked_duration,  # 50 ms in tests
                "static_variance_threshold": 0.0,             # disable static
                "static_duration_seconds": 9999.0,
                "tilted_angle_delta_degrees": 180.0,           # disable tilted
                "tilted_confirmation_frames": 9999,
                "frame_buffer_size": 10,
            },
        )

    def test_black_frame_triggers_blocked_event(self):
        """
        Feeding solid-black frames for longer than blocked_duration_seconds
        must produce a BLOCKED TamperEvent.
        """
        from backend.analyzers.tamper_detector import TamperType, TamperEvent

        detector = self._make_detector(blocked_duration=0.05)
        black = _make_black_frame()

        event: Optional[TamperEvent] = None

        # Feed frames until we get an event (or time out after 200 attempts).
        for _ in range(200):
            result = detector.analyze(black)
            time.sleep(0.001)
            if result is not None:
                event = result
                break

        assert event is not None, "Expected a BLOCKED TamperEvent but got None"
        assert event.tamper_type == TamperType.BLOCKED
        assert event.camera_id == "test-cam"
        assert 0.0 <= event.confidence <= 1.0

    def test_blocked_event_has_base64_snapshot(self):
        """The TamperEvent must carry a non-empty base-64 JPEG snapshot."""
        import base64
        from backend.analyzers.tamper_detector import TamperEvent

        detector = self._make_detector(blocked_duration=0.05)
        black = _make_black_frame()
        event: Optional[TamperEvent] = None
        for _ in range(200):
            result = detector.analyze(black)
            time.sleep(0.001)
            if result is not None:
                event = result
                break

        assert event is not None
        assert len(event.frame_snapshot_b64) > 0
        # Validate it is valid base64.
        decoded = base64.b64decode(event.frame_snapshot_b64)
        assert len(decoded) > 0

    def test_only_one_event_per_episode(self):
        """
        Once a BLOCKED event is emitted, subsequent frames in the same
        episode should NOT produce additional events (flood prevention).
        """
        from backend.analyzers.tamper_detector import TamperEvent

        detector = self._make_detector(blocked_duration=0.05)
        black = _make_black_frame()

        events: list[TamperEvent] = []
        for _ in range(300):
            result = detector.analyze(black)
            time.sleep(0.001)
            if result is not None:
                events.append(result)

        assert len(events) == 1, (
            f"Expected exactly 1 event per tamper episode, got {len(events)}"
        )

    def test_bright_frame_does_not_trigger_blocked(self):
        """A normally lit (bright) frame must not trigger BLOCKED."""
        detector = self._make_detector(blocked_duration=0.05)
        bright = np.full((480, 640, 3), fill_value=200, dtype=np.uint8)

        for _ in range(100):
            result = detector.analyze(bright)
            time.sleep(0.001)
            if result is not None:
                pytest.fail(
                    f"Unexpected tamper event on bright frame: {result.tamper_type}"
                )

    def test_blocked_confidence_is_one_for_pure_black(self):
        """
        A pure black frame has brightness=0, so confidence should be
        clamped to 1.0.
        """
        from backend.analyzers.tamper_detector import TamperEvent

        detector = self._make_detector(blocked_duration=0.05)
        black = _make_black_frame()
        event: Optional[TamperEvent] = None
        for _ in range(200):
            result = detector.analyze(black)
            time.sleep(0.001)
            if result is not None:
                event = result
                break

        assert event is not None
        assert event.confidence == 1.0
