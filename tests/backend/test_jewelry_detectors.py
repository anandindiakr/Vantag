"""
tests/backend/test_jewelry_detectors.py
=======================================
pytest suite for the jewellery-counter detection layer.

Covers:
1. JewelryScene        — polygon parsing, point-in-polygon, hand estimation
2. JewelryHandoverDetector — reach-in → withdraw emission + cooldown
3. GrabAndRunDetector  — case → fast exit sequencing + speed gating
4. JewelryTrayDetector — tray fill change + person-present gating

The detectors use ``time.monotonic()`` internally, so timing-sensitive
behaviour is driven through a fake clock patched onto each module's ``time``
name.  No OpenCV/numpy are required for these tests.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ─── Optional-dependency stubs (mirrors test_analyzers.py) ─────────────────
try:
    import numpy  # noqa: F401
except ModuleNotFoundError:
    import types
    _np = types.ModuleType("numpy")
    _np.mean = lambda *a, **kw: 0.0
    _np.zeros = lambda *a, **kw: []
    _np.ndarray = list
    _np.isscalar = lambda x: isinstance(x, (int, float, complex, bool))
    _np.bool_ = bool
    sys.modules["numpy"] = _np

try:
    import shapely  # noqa: F401
except ModuleNotFoundError:
    import types
    sys.modules["shapely"] = types.ModuleType("shapely")
    sys.modules["shapely.geometry"] = types.ModuleType("shapely.geometry")

try:
    import cv2  # noqa: F401
except ImportError:
    import types
    sys.modules["cv2"] = types.ModuleType("cv2")


# ─── Fake clock ─────────────────────────────────────────────────────────────
class FakeClock:
    """Controllable monotonic clock for time-sensitive analyzer tests."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def monotonic(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


# ─── Detection helpers ──────────────────────────────────────────────────────
@dataclass
class _Detection:
    track_id: int
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[int, int, int, int]
    keypoints: Optional[list] = None


def _person(track_id: int, bbox: Tuple[int, int, int, int]) -> _Detection:
    return _Detection(track_id, 0, "person", 0.9, bbox)


def _person_with_hands(
    track_id: int,
    bbox: Tuple[int, int, int, int],
    wrists: List[Tuple[float, float]],
) -> _Detection:
    """Person detection whose COCO keypoints place the wrists at *wrists*."""
    kps = [(0.0, 0.0, 0.0) for _ in range(17)]
    for idx, pos in zip((9, 10), wrists):
        kps[idx] = (pos[0], pos[1], 0.9)
    return _Detection(track_id, 0, "person", 0.9, bbox, keypoints=kps)


class FakeFrame:
    """Minimal frame stand-in exposing ``shape`` and slice access."""

    def __init__(self, h: int = 480, w: int = 640) -> None:
        self.shape = (h, w, 3)

    def __getitem__(self, key):
        return self


# ─────────────────────────────────────────────────────────────────────────────
# TEST GROUP 1: JewelryScene
# ─────────────────────────────────────────────────────────────────────────────

class TestJewelryScene:
    def test_point_in_polygon_inside_outside(self):
        from backend.analyzers.jewelry_scene import point_in_polygon
        poly = [(0, 0), (100, 0), (100, 100), (0, 100)]
        assert point_in_polygon(50, 50, poly) is True
        assert point_in_polygon(150, 150, poly) is False

    def test_point_in_polygon_none_is_false(self):
        from backend.analyzers.jewelry_scene import point_in_polygon
        assert point_in_polygon(0, 0, None) is False

    def test_parse_polygon_rejects_degenerate(self):
        from backend.analyzers.jewelry_scene import parse_polygon
        assert parse_polygon([]) is None
        assert parse_polygon([[0, 0], [10, 10]]) is None  # < 3 vertices

    def test_hand_points_prefer_wrists(self):
        from backend.analyzers.jewelry_scene import hand_points
        det = _person_with_hands(1, (0, 0, 100, 200), [(30, 30), (70, 70)])
        pts = hand_points(det)
        assert (30, 30) in pts
        assert (70, 70) in pts

    def test_hand_points_fallback_to_bbox(self):
        from backend.analyzers.jewelry_scene import hand_points
        det = _person(1, (0, 0, 100, 200))
        pts = hand_points(det)
        assert len(pts) == 5
        assert (50, 200) in pts  # bottom-centre

    def test_from_config_parses_trays_and_configured(self):
        from backend.analyzers.jewelry_scene import JewelryScene
        cfg = {
            "counter_polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
            "trays": [
                {"label": "case A", "polygon": [[10, 10], [90, 10], [90, 90], [10, 90]]}
            ],
        }
        scene = JewelryScene.from_config(cfg)
        assert scene.is_configured() is True
        assert scene.counter_polygon is not None
        assert len(scene.trays) == 1
        assert scene.trays[0]["label"] == "case A"

    def test_empty_config_not_configured(self):
        from backend.analyzers.jewelry_scene import JewelryScene
        assert JewelryScene.from_config({}).is_configured() is False


# ─────────────────────────────────────────────────────────────────────────────
# TEST GROUP 2: JewelryHandoverDetector
# ─────────────────────────────────────────────────────────────────────────────

_TRAY = [[10, 10], [90, 10], [90, 90], [10, 90]]
_COUNTER = [[0, 0], [200, 0], [200, 200], [0, 200]]


def _make_handover(clock: FakeClock, **overrides):
    import backend.analyzers.jewelry_handover as mod

    clock.advance(0)
    mod.time = clock

    cfg = {
        "counter_polygon": _COUNTER,
        "tray_polygon": _TRAY,
        "min_hand_inside_frames": 1,
        "cooldown_seconds": 30.0,
        "confidence_threshold": 0.45,
    }
    cfg.update(overrides)
    return mod.JewelryHandoverDetector(camera_id="cam-1", config=cfg)


class TestJewelryHandoverDetector:
    def test_disabled_without_tray_polygon(self):
        import backend.analyzers.jewelry_handover as mod
        clock = FakeClock()
        mod.time = clock
        det = mod.JewelryHandoverDetector("cam-1", {"tray_polygon": []})
        assert det.analyze(object(), [_person(1, (0, 0, 100, 200))], 0.0) == []

    def test_no_event_without_reach(self):
        clock = FakeClock()
        det = _make_handover(clock)
        # Hand points (bbox fallback) stay outside the tray polygon.
        person = _person(1, (0, 0, 100, 200))
        assert det.analyze(object(), [person], 0.0) == []

    def test_reach_then_withdraw_emits(self):
        from backend.analyzers.jewelry_handover import HandoverEvent
        clock = FakeClock()
        det = _make_handover(clock)

        # Hand (wrist) inside the tray.
        inside = _person_with_hands(1, (0, 0, 200, 200), [(50, 50), (50, 50)])
        # Hand withdrawn (wrist far outside the tray).
        outside = _person_with_hands(1, (0, 0, 200, 200), [(150, 150), (150, 150)])

        assert det.analyze(object(), [inside], 0.0) == []   # reach begins
        events = det.analyze(object(), [outside], 0.0)      # withdraw
        assert len(events) == 1
        assert isinstance(events[0], HandoverEvent)
        assert events[0].person_track_id == 1
        assert events[0].event_subtype == "reach_in_withdraw"

    def test_min_frames_gate(self):
        clock = FakeClock()
        det = _make_handover(clock, min_hand_inside_frames=3)

        inside = _person_with_hands(1, (0, 0, 200, 200), [(50, 50), (50, 50)])
        outside = _person_with_hands(1, (0, 0, 200, 200), [(150, 150), (150, 150)])

        det.analyze(object(), [inside], 0.0)  # frame 1 of reach
        events = det.analyze(object(), [outside], 0.0)  # withdraw too early
        assert events == [], "Withdraw before min frames must not emit"

    def test_cooldown_suppresses_repeat(self):
        clock = FakeClock()
        det = _make_handover(clock, cooldown_seconds=30.0)

        inside = _person_with_hands(1, (0, 0, 200, 200), [(50, 50), (50, 50)])
        outside = _person_with_hands(1, (0, 0, 200, 200), [(150, 150), (150, 150)])

        det.analyze(object(), [inside], 0.0)
        e1 = det.analyze(object(), [outside], 0.0)
        assert len(e1) == 1

        # Second episode immediately — within cooldown.
        det.analyze(object(), [inside], 0.0)
        e2 = det.analyze(object(), [outside], 0.0)
        assert e2 == []

        # After cooldown elapses, a third episode emits again.
        clock.advance(31.0)
        det.analyze(object(), [inside], 0.0)
        e3 = det.analyze(object(), [outside], 0.0)
        assert len(e3) == 1


# ─────────────────────────────────────────────────────────────────────────────
# TEST GROUP 3: GrabAndRunDetector
# ─────────────────────────────────────────────────────────────────────────────

_CASE = [[100, 100], [300, 100], [300, 300], [100, 300]]
_EXIT = [[400, 400], [600, 400], [600, 600], [400, 600]]


def _make_grab(clock: FakeClock, **overrides):
    import backend.analyzers.grab_and_run as mod

    mod.time = clock

    cfg = {
        "case_polygon": _CASE,
        "exit_polygon": _EXIT,
        "approach_polygon": [],
        "max_window_seconds": 8.0,
        "min_exit_speed_px_s": 120.0,
        "cooldown_seconds": 30.0,
        "confidence_threshold": 0.45,
    }
    cfg.update(overrides)
    return mod.GrabAndRunDetector(camera_id="cam-1", config=cfg)


class TestGrabAndRunDetector:
    def test_disabled_without_zones(self):
        import backend.analyzers.grab_and_run as mod
        clock = FakeClock()
        mod.time = clock
        det = mod.GrabAndRunDetector("cam-1", {})
        assert det.analyze(object(), [_person(1, (200, 200, 300, 300))], 0.0) == []

    def test_fast_case_to_exit_emits(self):
        from backend.analyzers.grab_and_run import GrabAndRunEvent
        clock = FakeClock()
        det = _make_grab(clock)

        # Person at the case, then at the exit 2s later (≈212 px / 2s = 106... use
        # a larger separation so the speed clearly exceeds the threshold).
        det.analyze(object(), [_person(1, (150, 150, 250, 250))], 0.0)  # in case
        clock.advance(2.0)
        events = det.analyze(object(), [_person(1, (450, 450, 550, 550))], 0.0)  # in exit
        assert len(events) == 1
        assert isinstance(events[0], GrabAndRunEvent)
        assert events[0].travel_seconds == pytest.approx(2.0, abs=0.01)

    def test_slow_exit_no_event(self):
        clock = FakeClock()
        det = _make_grab(clock, min_exit_speed_px_s=5000.0)  # impossible speed

        det.analyze(object(), [_person(1, (150, 150, 250, 250))], 0.0)
        clock.advance(2.0)
        events = det.analyze(object(), [_person(1, (450, 450, 550, 550))], 0.0)
        assert events == []

    def test_window_expiry_no_event(self):
        clock = FakeClock()
        det = _make_grab(clock, max_window_seconds=5.0)

        det.analyze(object(), [_person(1, (150, 150, 250, 250))], 0.0)
        clock.advance(6.0)  # beyond the window
        events = det.analyze(object(), [_person(1, (450, 450, 550, 550))], 0.0)
        assert events == []

    def test_approach_gate_blocks_without_approach(self):
        clock = FakeClock()
        det = _make_grab(
            clock,
            approach_polygon=[[0, 0], [90, 0], [90, 90], [0, 90]],
        )

        # Skip the approach polygon entirely.
        det.analyze(object(), [_person(1, (150, 150, 250, 250))], 0.0)
        clock.advance(2.0)
        events = det.analyze(object(), [_person(1, (450, 450, 550, 550))], 0.0)
        assert events == []

    def test_approach_gate_passes_after_approach(self):
        from backend.analyzers.grab_and_run import GrabAndRunEvent
        clock = FakeClock()
        det = _make_grab(
            clock,
            approach_polygon=[[0, 0], [90, 0], [90, 90], [0, 90]],
        )

        det.analyze(object(), [_person(1, (40, 40, 80, 80))], 0.0)   # approach
        det.analyze(object(), [_person(1, (150, 150, 250, 250))], 0.0)  # case
        clock.advance(2.0)
        events = det.analyze(object(), [_person(1, (450, 450, 550, 550))], 0.0)
        assert len(events) == 1
        assert isinstance(events[0], GrabAndRunEvent)


# ─────────────────────────────────────────────────────────────────────────────
# TEST GROUP 4: JewelryTrayDetector
# ─────────────────────────────────────────────────────────────────────────────

def _make_tray(clock: FakeClock, **overrides):
    import backend.analyzers.jewelry_tray as mod

    mod.time = clock

    cfg = {
        "trays": [{"label": "case A", "polygon": _TRAY}],
        "counter_polygon": _COUNTER,
        "drop_ratio_threshold": 0.25,
        "check_interval_seconds": 0.0,
        "cooldown_seconds": 30.0,
        "person_required": True,
        "confidence_threshold": 0.45,
    }
    cfg.update(overrides)
    det = mod.JewelryTrayDetector(camera_id="cam-1", config=cfg)
    return det


class TestJewelryTrayDetector:
    def test_disabled_without_trays(self):
        import backend.analyzers.jewelry_tray as mod
        clock = FakeClock()
        mod.time = clock
        det = mod.JewelryTrayDetector("cam-1", {})
        assert det.analyze(FakeFrame(), [_person(1, (50, 50, 150, 150))], 0.0) == []

    def test_fill_drop_with_person_emits(self):
        from backend.analyzers.jewelry_tray import TrayEvent
        clock = FakeClock()
        det = _make_tray(clock)

        # Two observations: baseline 0.9, then 0.5 (drop of 0.4 ≥ 0.25).
        fills = iter([0.9, 0.5])
        det._fill_ratio = lambda state, roi: next(fills)

        person = _person(1, (50, 50, 150, 150))  # centroid inside counter
        assert det.analyze(FakeFrame(), [person], 0.0) == []  # baseline
        events = det.analyze(FakeFrame(), [person], 0.0)
        assert len(events) == 1
        assert isinstance(events[0], TrayEvent)
        assert events[0].change_type == "removed"
        assert events[0].tray_label == "case A"
        assert events[0].person_present is True

    def test_person_required_suppresses_without_person(self):
        clock = FakeClock()
        det = _make_tray(clock, person_required=True)

        fills = iter([0.9, 0.5])
        det._fill_ratio = lambda state, roi: next(fills)

        # No person near the counter — no events at all.
        assert det.analyze(FakeFrame(), [], 0.0) == []
        assert det.analyze(FakeFrame(), [], 0.0) == []

    def test_person_required_false_emits_without_person(self):
        from backend.analyzers.jewelry_tray import TrayEvent
        clock = FakeClock()
        det = _make_tray(clock, person_required=False)

        fills = iter([0.9, 0.5])
        det._fill_ratio = lambda state, roi: next(fills)

        det.analyze(FakeFrame(), [], 0.0)
        events = det.analyze(FakeFrame(), [], 0.0)
        assert len(events) == 1
        assert isinstance(events[0], TrayEvent)

    def test_baseline_first_observation_no_event(self):
        clock = FakeClock()
        det = _make_tray(clock)
        det._fill_ratio = lambda state, roi: 0.9
        person = _person(1, (50, 50, 150, 150))
        assert det.analyze(FakeFrame(), [person], 0.0) == []

    def test_small_change_no_event(self):
        clock = FakeClock()
        det = _make_tray(clock)
        fills = iter([0.9, 0.85])  # delta 0.05 < 0.25*0.5
        det._fill_ratio = lambda state, roi: next(fills)
        person = _person(1, (50, 50, 150, 150))
        det.analyze(FakeFrame(), [person], 0.0)
        assert det.analyze(FakeFrame(), [person], 0.0) == []

    def test_cooldown_suppresses_repeat(self):
        clock = FakeClock()
        det = _make_tray(clock, cooldown_seconds=30.0)

        fills = iter([0.9, 0.5, 0.9, 0.5])
        det._fill_ratio = lambda state, roi: next(fills)

        person = _person(1, (50, 50, 150, 150))
        det.analyze(FakeFrame(), [person], 0.0)          # baseline 0.9
        e1 = det.analyze(FakeFrame(), [person], 0.0)     # drop → event
        assert len(e1) == 1

        det.analyze(FakeFrame(), [person], 0.0)          # back up 0.9 (appear? gated by cooldown)
        e2 = det.analyze(FakeFrame(), [person], 0.0)     # drop again — within cooldown
        assert e2 == []
