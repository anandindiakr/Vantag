"""
Local test script for FallDetector and LoiteringDetector.

No camera, no RTSP, no ONNX model required.
Simulates bounding-box sequences and verifies events fire at the right time.

Usage (from repo root):
    cd windows_agent
    python test_detectors.py

Pass/fail summary printed at the end. Exit code 0 = all pass.
"""
import sys
import time
import types
import numpy as np

# ── Minimal BoundingBox stub (mirrors inference.BoundingBox) ─────────────────
class BoundingBox:
    def __init__(self, x, y, w, h, label="person", confidence=0.9):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.label = label
        self.confidence = confidence

    def to_dict(self):
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}


# ── Patch the agent package so we don't need cv2 / onnxruntime installed ─────
# Create a fake 'agent' package in sys.modules pointing at the real source dir.
import importlib, pathlib

_AGENT_DIR = pathlib.Path(__file__).parent / "agent"
sys.path.insert(0, str(_AGENT_DIR.parent))  # windows_agent/ on path

# Stub out heavy imports before camera_worker loads them
_cv2_stub = types.ModuleType("cv2")
_cv2_stub.resize = lambda img, size: img
_cv2_stub.imencode = lambda ext, img, params=None: (True, np.zeros((1,), dtype=np.uint8))
_cv2_stub.VideoCapture = None
_cv2_stub.CAP_FFMPEG = 0
_cv2_stub.CAP_PROP_BUFFERSIZE = 0
_cv2_stub.IMWRITE_JPEG_QUALITY = 1
sys.modules["cv2"] = _cv2_stub

_np_stub_mod = types.ModuleType("numpy")
sys.modules.setdefault("numpy", np)  # real numpy is fine

# Stub inference module
_inf_stub = types.ModuleType("agent.inference")
_inf_stub.YoloInference = object
_inf_stub.RETAIL_CLASSES = {
    "backpack": "high_value_item",
    "handbag": "high_value_item",
    "bottle": "shelf_item",
    "cup": "shelf_item",
}
sys.modules["agent.inference"] = _inf_stub

# Stub config + api_client
_cfg_stub = types.ModuleType("agent.config")
class _FakeCamConfig:
    id = "test-cam"
    name = "Test Camera"
    rtsp_url = "rtsp://fake"
_cfg_stub.CameraConfig = _FakeCamConfig
sys.modules["agent.config"] = _cfg_stub

_api_stub = types.ModuleType("agent.api_client")
class _FakeApi:
    def post_event(self, evt): pass
_api_stub.VantagApiClient = _FakeApi
sys.modules["agent.api_client"] = _api_stub

# Now import the real detectors
from agent.camera_worker import (
    FallDetector,
    LoiteringDetector,
    CrowdDetector,
    SuspiciousBehaviorDetector,
    DetectionAnalyzer,
)
import collections

# ── Helpers ───────────────────────────────────────────────────────────────────
BLANK_FRAME = np.zeros((180, 320, 3), dtype=np.uint8)

def _person(x=0.3, y=0.3, w=0.1, h=0.3, confidence=0.9):
    return BoundingBox(x, y, w, h, "person", confidence)

_PASS = []
_FAIL = []

def check(name: str, condition: bool, detail: str = ""):
    if condition:
        _PASS.append(name)
        print(f"  [PASS] {name}")
    else:
        _FAIL.append(name)
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. FallDetector — standing person should NOT trigger
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- FallDetector ---")

def test_fall_no_trigger_when_standing():
    fd = FallDetector("cam1", cooldown_sec=1)
    # h/w = 0.3/0.1 = 3.0 → always upright, never fallen
    p = _person(w=0.10, h=0.30)
    for _ in range(30):
        evt = fd.analyse([p], BLANK_FRAME)
    check("no fall when always standing", evt is None)

def test_fall_triggers_after_transition():
    fd = FallDetector("cam1", cooldown_sec=1)
    # Feed 15 upright frames (h/w = 3.5)
    for _ in range(15):
        fd.analyse([_person(w=0.08, h=0.28)], BLANK_FRAME)
    # Then feed fallen frames (h/w = 0.39 → below FALL_RATIO=0.75)
    # Collect ALL return values — event fires on the frame where threshold is
    # first met; subsequent frames within cooldown return None.
    events = [fd.analyse([_person(w=0.28, h=0.11)], BLANK_FRAME) for _ in range(5)]
    evt = next((e for e in events if e is not None), None)
    check("fall_detected fires after stand->fall transition",
          evt is not None and evt["event_type"] == "fall_detected",
          f"got {evt}")

def test_fall_severity_is_high():
    fd = FallDetector("cam1", cooldown_sec=1)
    for _ in range(15):
        fd.analyse([_person(w=0.08, h=0.28)], BLANK_FRAME)
    events = [fd.analyse([_person(w=0.28, h=0.11)], BLANK_FRAME) for _ in range(5)]
    evt = next((e for e in events if e is not None), None)
    check("fall_detected severity=high",
          evt is not None and evt.get("severity") == "high",
          f"severity={evt.get('severity') if evt else 'None'}")

def test_fall_cooldown_prevents_repeat():
    fd = FallDetector("cam1", cooldown_sec=60)  # long cooldown
    for _ in range(15):
        fd.analyse([_person(w=0.08, h=0.28)], BLANK_FRAME)
    events = []
    for _ in range(10):
        evt = fd.analyse([_person(w=0.28, h=0.11)], BLANK_FRAME)
        if evt:
            events.append(evt)
    check("fall cooldown prevents duplicate alerts within window",
          len(events) <= 1,
          f"got {len(events)} events")

def test_fall_no_trigger_without_prior_standing():
    fd = FallDetector("cam1", cooldown_sec=1)
    # Person appears already fallen — no upright history → should NOT fire
    evt = None
    for _ in range(12):
        evt = fd.analyse([_person(w=0.28, h=0.11)], BLANK_FRAME)
    check("no fall alert when no prior upright history",
          evt is None,
          f"got {evt}")

test_fall_no_trigger_when_standing()
test_fall_triggers_after_transition()
test_fall_severity_is_high()
test_fall_cooldown_prevents_repeat()
test_fall_no_trigger_without_prior_standing()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LoiteringDetector
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- LoiteringDetector ---")

def test_loiter_no_trigger_below_threshold():
    ld = LoiteringDetector("cam1", cooldown_sec=1)
    # Only 5 seconds presence — well below 90s threshold
    ld._zones = {}
    p = _person(x=0.3, y=0.3)
    for _ in range(10):
        evt = ld.analyse([p], BLANK_FRAME)
    check("no loitering below time threshold", evt is None)

def test_loiter_triggers_after_long_presence():
    ld = LoiteringDetector("cam1", cooldown_sec=1)
    # Person centre = (0.45+0.05, 0.45+0.05) = (0.50, 0.50)
    # Cell = int(0.50 * 3) = 1 → "1_1"
    import collections
    cell = "1_1"
    ld._zones[cell] = {
        "first_seen": time.time() - 95,
        "positions": collections.deque(
            # Movement spanning ~0.15 in x and 0.09 in y → variance 0.24 >> 0.06
            [(0.44 + i * 0.005, 0.47 + i * 0.003) for i in range(30)],
            maxlen=50,
        ),
        "last_event": 0.0,
    }
    p = _person(x=0.45, y=0.45, w=0.10, h=0.10)
    evt = ld.analyse([p], BLANK_FRAME)
    check("loitering fires after threshold presence with movement",
          evt is not None and evt["event_type"] == "loitering",
          f"got {evt}")

def test_loiter_no_trigger_if_stationary():
    ld = LoiteringDetector("cam1", cooldown_sec=1)
    import collections
    cell = "1_1"
    # All positions identical at (0.50, 0.50) — zero variance
    # Person also centres at (0.50, 0.50) so appended value adds no spread
    ld._zones[cell] = {
        "first_seen": time.time() - 95,
        "positions": collections.deque(
            [(0.50, 0.50)] * 30,
            maxlen=50,
        ),
        "last_event": 0.0,
    }
    p = _person(x=0.45, y=0.45, w=0.10, h=0.10)
    evt = ld.analyse([p], BLANK_FRAME)
    check("no loitering when person is completely stationary (dwell, not loiter)",
          evt is None,
          f"got {evt}")

def test_loiter_severity_low():
    ld = LoiteringDetector("cam1", cooldown_sec=1)
    import collections
    cell = "1_1"
    ld._zones[cell] = {
        "first_seen": time.time() - 95,
        "positions": collections.deque(
            [(0.44 + i * 0.005, 0.47 + i * 0.003) for i in range(30)],
            maxlen=50,
        ),
        "last_event": 0.0,
    }
    p = _person(x=0.45, y=0.45, w=0.10, h=0.10)
    evt = ld.analyse([p], BLANK_FRAME)
    check("loitering severity=low",
          evt is not None and evt.get("severity") == "low",
          f"severity={evt.get('severity') if evt else 'None'}")

def test_loiter_zone_cleared_when_person_leaves():
    ld = LoiteringDetector("cam1", cooldown_sec=60)
    # Seed a zone
    import collections
    ld._zones["1_1"] = {
        "first_seen": time.time() - 100,
        "positions": collections.deque(maxlen=50),
        "last_event": 0.0,
    }
    # No persons in frame → zone should be removed
    ld.analyse([], BLANK_FRAME)
    check("zone cleared when person leaves frame",
          "1_1" not in ld._zones)

test_loiter_no_trigger_below_threshold()
test_loiter_triggers_after_long_presence()
test_loiter_no_trigger_if_stationary()
test_loiter_severity_low()
test_loiter_zone_cleared_when_person_leaves()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. DetectionAnalyzer integration — all 5 event types
# ═══════════════════════════════════════════════════════════════════════════════
print("\n--- DetectionAnalyzer (integration) ---")

def test_analyzer_shoplifting():
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    person = _person(x=0.30, y=0.30, w=0.10, h=0.15)
    bag    = BoundingBox(x=0.32, y=0.32, w=0.08, h=0.12, label="backpack", confidence=0.85)
    # Item key: "sweep_{int(0.32*10)}_{int(0.32*10)}" = "sweep_3_3"
    # Seed it 3s ago so the 2s threshold is already met.
    da._person_with_items["sweep_3_3"] = time.time() - 3.0
    events = da.analyse([person, bag], BLANK_FRAME)
    types_seen = {e["event_type"] for e in events}
    check("shoplifting fires when person overlaps high-value item for >2s",
          "shoplifting" in types_seen,
          f"events={types_seen}")

def test_analyzer_inventory_movement():
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    # Force _shelf_empty_since to 65 seconds ago
    da._shelf_empty_since = time.time() - 65
    events = da.analyse([], BLANK_FRAME)
    types_seen = {e["event_type"] for e in events}
    check("inventory_movement fires when shelf empty >60s",
          "inventory_movement" in types_seen,
          f"events={types_seen}")

def test_analyzer_fall_integration():
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    # Feed upright frames then fallen frames
    for _ in range(15):
        da.analyse([_person(w=0.08, h=0.28)], BLANK_FRAME)
    events = []
    for _ in range(5):
        events += da.analyse([_person(w=0.28, h=0.11)], BLANK_FRAME)
    types_seen = {e["event_type"] for e in events}
    check("fall_detected emitted through DetectionAnalyzer",
          "fall_detected" in types_seen,
          f"events={types_seen}")

def test_analyzer_loitering_integration():
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    import collections
    cell = "1_1"
    da._loiter_detector._zones[cell] = {
        "first_seen": time.time() - 95,
        "positions": collections.deque(
            [(0.44 + i * 0.005, 0.47 + i * 0.003) for i in range(30)],
            maxlen=50,
        ),
        "last_event": 0.0,
    }
    # centre (0.50, 0.50) → cell "1_1"
    p = _person(x=0.45, y=0.45, w=0.10, h=0.10)
    events = da.analyse([p], BLANK_FRAME)
    types_seen = {e["event_type"] for e in events}
    check("loitering emitted through DetectionAnalyzer",
          "loitering" in types_seen,
          f"events={types_seen}")

test_analyzer_shoplifting()
test_analyzer_inventory_movement()
test_analyzer_fall_integration()
test_analyzer_loitering_integration()


# =============================================================================
# 4. Shoplifting timer — YOLO realism
#    Each "frame" creates NEW BoundingBox instances (just like real YOLO).
#    Item position is fixed; person position jitters or drifts.
# =============================================================================
print("\n--- Shoplifting timer: YOLO realism ---")

import random as _random
_random.seed(42)

def _yolo_frame(person_cx, person_cy, item_cx, item_cy,
                person_jitter=0.003, item_jitter=0.001):
    """
    Simulate one YOLO inference output:
      - New BoundingBox objects created from scratch (like real postprocess())
      - Small Gaussian noise added (1-2px at 640p ≈ 0.002-0.003 normalised)
    """
    pw, ph = 0.10, 0.20
    iw, ih = 0.08, 0.12
    px = person_cx - pw/2 + _random.gauss(0, person_jitter)
    py = person_cy - ph/2 + _random.gauss(0, person_jitter)
    ix = item_cx   - iw/2 + _random.gauss(0, item_jitter)
    iy = item_cy   - ih/2 + _random.gauss(0, item_jitter)
    return (
        BoundingBox(max(0,px), max(0,py), pw, ph, "person",  0.88),
        BoundingBox(max(0,ix), max(0,iy), iw, ih, "backpack", 0.91),
    )

def test_shoplifting_jitter_safe():
    """
    Stationary person near item with realistic ±3px YOLO jitter.
    New BoundingBox objects each frame. Timer must accumulate and fire.
    """
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    # Back-date the item's slot 3s (key is item-anchored, so jitter on person is irrelevant)
    item_cx, item_cy = 0.55, 0.45
    iw, ih = 0.08, 0.12
    item_key = f"sweep_{int((item_cx - iw/2)*10)}_{int((item_cy - ih/2)*10)}"
    da._person_with_items[item_key] = time.time() - 3.0

    all_events = []
    for _ in range(10):
        p, item = _yolo_frame(0.52, 0.47, item_cx, item_cy)
        all_events += da.analyse([p, item], BLANK_FRAME)

    types_seen = {e["event_type"] for e in all_events}
    check("shoplifting fires despite per-frame YOLO jitter (new objects each frame)",
          "shoplifting" in types_seen,
          f"events={types_seen}")

def test_shoplifting_slow_walk_fires():
    """
    Person drifts 5px/frame (slow browse) — crosses 64px cell in ~13 frames.
    With item-anchored key the timer must still fire at 2s (5 frames @ 2.5 AI fps).
    """
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    item_cx, item_cy = 0.55, 0.45
    iw, ih = 0.08, 0.12
    item_key = f"sweep_{int((item_cx - iw/2)*10)}_{int((item_cy - ih/2)*10)}"
    da._person_with_items[item_key] = time.time() - 3.0

    all_events = []
    for i in range(15):
        # Person drifts +5px per frame (0.0078 normalised/frame)
        drift = i * (5 / 640)
        p, item = _yolo_frame(0.52 + drift, 0.47, item_cx, item_cy)
        all_events += da.analyse([p, item], BLANK_FRAME)

    types_seen = {e["event_type"] for e in all_events}
    check("shoplifting fires for slow-walking person (item-anchored key stable)",
          "shoplifting" in types_seen,
          f"events={types_seen}")

def test_shoplifting_brisk_walk_fires():
    """
    Person drifts 15px/frame (brisk walk — would break old person-anchored key
    in ~1.7s, before the 2s timer). Item-anchored key must fire correctly.
    """
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    item_cx, item_cy = 0.55, 0.45
    iw, ih = 0.08, 0.12
    item_key = f"sweep_{int((item_cx - iw/2)*10)}_{int((item_cy - ih/2)*10)}"
    da._person_with_items[item_key] = time.time() - 3.0

    all_events = []
    for i in range(10):
        drift = i * (15 / 640)
        p, item = _yolo_frame(0.52 + drift, 0.47, item_cx, item_cy)
        all_events += da.analyse([p, item], BLANK_FRAME)

    types_seen = {e["event_type"] for e in all_events}
    check("shoplifting fires for brisk-walking person (would fail with old person key)",
          "shoplifting" in types_seen,
          f"events={types_seen}")

def test_shoplifting_different_items_independent():
    """
    Two backpacks in different shelf positions. Timer on bag-A fires without
    contaminating bag-B's slot, and vice-versa.
    """
    da = DetectionAnalyzer("cam1", cooldown_sec=60, fps=5.0)  # long cooldown
    # Item A at left shelf, Item B at right shelf (different int(x*10) cells)
    item_a = BoundingBox(0.20, 0.40, 0.08, 0.12, "backpack", 0.90)
    item_b = BoundingBox(0.70, 0.40, 0.08, 0.12, "backpack", 0.90)
    person = BoundingBox(0.18, 0.38, 0.10, 0.20, "person", 0.88)

    key_a = f"sweep_{int(0.20*10)}_{int(0.40*10)}"
    key_b = f"sweep_{int(0.70*10)}_{int(0.40*10)}"

    # Only seed item-A's timer
    da._person_with_items[key_a] = time.time() - 3.0

    # Person overlaps item-A only
    events = da.analyse([person, item_a, item_b], BLANK_FRAME)
    types_seen = {e["event_type"] for e in events}

    check("shoplifting fires for item-A only; item-B slot not contaminated",
          "shoplifting" in types_seen and key_b not in da._person_with_items,
          f"events={types_seen}, keys={list(da._person_with_items.keys())}")

test_shoplifting_jitter_safe()
test_shoplifting_slow_walk_fires()
test_shoplifting_brisk_walk_fires()
test_shoplifting_different_items_independent()


# =============================================================================
# 5. Restricted Zone (via DetectionAnalyzer dwell-frame counter)
#    Fires when a person stays in the same coarse cell for >30s worth of frames.
# =============================================================================
print("\n--- Restricted Zone (DetectionAnalyzer) ---")

def _dwell_key(da):
    """Return the single 'dwell_' key the analyzer created (float-rounding safe)."""
    return next((k for k in da._person_frame_counts if k.startswith("dwell_")), None)

def test_restricted_zone_fires_after_frame_threshold():
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    p = _person(x=0.30, y=0.30, w=0.10, h=0.15, confidence=0.70)
    da.analyse([p], BLANK_FRAME)             # creates the dwell key (count=1)
    key = _dwell_key(da)
    da._person_frame_counts[key] = int(30 * da.fps) - 1   # one short of threshold
    events = da.analyse([p], BLANK_FRAME)    # count hits threshold → fires
    types_seen = {e["event_type"] for e in events}
    check("restricted_zone fires after >30s stationary presence",
          "restricted_zone" in types_seen,
          f"events={types_seen}")

def test_restricted_zone_no_fire_below_threshold():
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    p = _person(x=0.30, y=0.30, w=0.10, h=0.15, confidence=0.70)
    da.analyse([p], BLANK_FRAME)
    key = _dwell_key(da)
    da._person_frame_counts[key] = 5         # well below 150
    events = da.analyse([p], BLANK_FRAME)
    types_seen = {e["event_type"] for e in events}
    check("no restricted_zone below frame threshold",
          "restricted_zone" not in types_seen,
          f"events={types_seen}")

def test_restricted_zone_counter_resets_after_fire():
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    p = _person(x=0.30, y=0.30, w=0.10, h=0.15, confidence=0.70)
    da.analyse([p], BLANK_FRAME)
    key = _dwell_key(da)
    da._person_frame_counts[key] = int(30 * da.fps) - 1
    da.analyse([p], BLANK_FRAME)             # fires, then resets counter
    check("restricted_zone frame counter resets to 0 after firing",
          da._person_frame_counts.get(key) == 0,
          f"count={da._person_frame_counts.get(key)}")

def test_restricted_zone_severity_medium():
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    # confidence 0.70 < 0.85 → severity stays 'medium' (not auto-promoted)
    p = _person(x=0.30, y=0.30, w=0.10, h=0.15, confidence=0.70)
    da.analyse([p], BLANK_FRAME)
    key = _dwell_key(da)
    da._person_frame_counts[key] = int(30 * da.fps) - 1
    events = da.analyse([p], BLANK_FRAME)
    evt = next((e for e in events if e["event_type"] == "restricted_zone"), None)
    check("restricted_zone severity=medium",
          evt is not None and evt.get("severity") == "medium",
          f"severity={evt.get('severity') if evt else 'None'}")

test_restricted_zone_fires_after_frame_threshold()
test_restricted_zone_no_fire_below_threshold()
test_restricted_zone_counter_resets_after_fire()
test_restricted_zone_severity_medium()


# =============================================================================
# 6. CrowdDetector
#    Fires when person count >= threshold sustained for SUSTAIN_SEC.
# =============================================================================
print("\n--- CrowdDetector ---")

def _persons(n):
    # Spread persons across the frame; only the count matters to CrowdDetector.
    return [_person(x=min(0.05 * i, 0.9), y=0.4, w=0.05, h=0.15) for i in range(n)]

def test_crowd_no_fire_below_count():
    cd = CrowdDetector("cam1", cooldown_sec=1)   # cooldown forced to >=60
    evt = None
    for _ in range(20):
        evt = cd.analyse(_persons(4), BLANK_FRAME)   # 4 < MIN_PERSONS(5)
    check("no crowding when count below threshold", evt is None, f"got {evt}")

def test_crowd_no_fire_before_sustain():
    cd = CrowdDetector("cam1", cooldown_sec=1)
    evt1 = cd.analyse(_persons(6), BLANK_FRAME)   # sets crowd_since=now
    evt2 = cd.analyse(_persons(6), BLANK_FRAME)   # now-crowd_since ~0 < 5s
    check("no crowding before sustain window elapses",
          evt1 is None and evt2 is None,
          f"evt1={evt1}, evt2={evt2}")

def test_crowd_fires_after_sustain():
    cd = CrowdDetector("cam1", cooldown_sec=1)
    cd._crowd_since = time.time() - 6.0           # backdate past SUSTAIN_SEC(5)
    evt = cd.analyse(_persons(6), BLANK_FRAME)
    check("crowding fires after sustained over-threshold count",
          evt is not None and evt["event_type"] == "crowding",
          f"got {evt}")

def test_crowd_severity_scales_with_count():
    cd = CrowdDetector("cam1", cooldown_sec=1)
    cd._crowd_since = time.time() - 6.0
    evt = cd.analyse(_persons(10), BLANK_FRAME)    # 10 >= MIN_PERSONS*2 → high
    check("crowding severity=high when count >= 2x threshold",
          evt is not None and evt.get("severity") == "high",
          f"severity={evt.get('severity') if evt else 'None'}")

def test_crowd_resets_when_count_drops():
    cd = CrowdDetector("cam1", cooldown_sec=1)
    cd._crowd_since = time.time() - 3.0
    cd.analyse(_persons(3), BLANK_FRAME)           # below threshold → reset
    check("crowd timer resets when count drops below threshold",
          cd._crowd_since is None,
          f"crowd_since={cd._crowd_since}")

test_crowd_no_fire_below_count()
test_crowd_no_fire_before_sustain()
test_crowd_fires_after_sustain()
test_crowd_severity_scales_with_count()
test_crowd_resets_when_count_drops()


# =============================================================================
# 7. SuspiciousBehaviorDetector
#    Fires on repeated horizontal direction reversals (pacing / casing) within
#    a single grid cell, once the per-cell history window is full.
# =============================================================================
print("\n--- SuspiciousBehaviorDetector ---")

def _pacing_person(high: bool):
    # Oscillate centre-x between 0.55 and 0.70 (swing 0.15 >> MIN_AMPLITUDE 0.04).
    # Both centres map to grid cell x=int(cx*4)=2; cy fixed at cell 2 → "2_2".
    cx = 0.70 if high else 0.55
    return _person(x=cx - 0.05, y=0.50, w=0.10, h=0.20)

def test_suspicious_no_fire_straight_walk():
    sd = SuspiciousBehaviorDetector("cam1", cooldown_sec=1)
    evt = None
    # Monotonic drift within one cell (0.55→0.70): direction never reverses.
    for i in range(25):
        cx = 0.55 + i * (0.006)              # stays < 0.70 → cell "2_2"
        p = _person(x=cx - 0.05, y=0.50, w=0.10, h=0.20)
        evt = sd.analyse([p], BLANK_FRAME)
    check("no suspicious_behavior for straight/monotonic movement",
          evt is None, f"got {evt}")

def test_suspicious_fires_on_pacing():
    sd = SuspiciousBehaviorDetector("cam1", cooldown_sec=1)
    events = []
    for i in range(22):
        events.append(sd.analyse([_pacing_person(i % 2 == 0)], BLANK_FRAME))
    evt = next((e for e in events if e is not None), None)
    check("suspicious_behavior fires on repeated direction reversals (pacing)",
          evt is not None and evt["event_type"] == "suspicious_behavior",
          f"got {evt}")

def test_suspicious_severity_medium():
    sd = SuspiciousBehaviorDetector("cam1", cooldown_sec=1)
    events = []
    for i in range(22):
        events.append(sd.analyse([_pacing_person(i % 2 == 0)], BLANK_FRAME))
    evt = next((e for e in events if e is not None), None)
    check("suspicious_behavior severity=medium",
          evt is not None and evt.get("severity") == "medium",
          f"severity={evt.get('severity') if evt else 'None'}")

def test_suspicious_track_cleared_on_exit():
    sd = SuspiciousBehaviorDetector("cam1", cooldown_sec=1)
    sd._tracks["2_2"] = collections.deque([0.5] * 20, maxlen=20)
    sd._last_event["2_2"] = time.time()
    sd.analyse([], BLANK_FRAME)              # nobody in frame → drop the track
    check("suspicious track cleared when person leaves frame",
          "2_2" not in sd._tracks and "2_2" not in sd._last_event,
          f"tracks={list(sd._tracks.keys())}")

def test_analyzer_suspicious_integration():
    da = DetectionAnalyzer("cam1", cooldown_sec=1, fps=5.0)
    events = []
    for i in range(22):
        events += da.analyse([_pacing_person(i % 2 == 0)], BLANK_FRAME)
    types_seen = {e["event_type"] for e in events}
    check("suspicious_behavior emitted through DetectionAnalyzer",
          "suspicious_behavior" in types_seen,
          f"events={types_seen}")

test_suspicious_no_fire_straight_walk()
test_suspicious_fires_on_pacing()
test_suspicious_severity_medium()
test_suspicious_track_cleared_on_exit()
test_analyzer_suspicious_integration()


# =============================================================================
# Summary
# =============================================================================
total = len(_PASS) + len(_FAIL)
print(f"\n{'='*60}")
print(f"Results: {len(_PASS)}/{total} passed")
if _FAIL:
    print(f"\nFailed tests:")
    for name in _FAIL:
        print(f"  - {name}")
    print()
    sys.exit(1)
else:
    print("All tests passed.")
    sys.exit(0)
