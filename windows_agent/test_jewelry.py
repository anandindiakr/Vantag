"""
Self-contained test for the High-Value Counter detectors (agent/jewelry.py).

No camera, no RTSP, no ONNX, no cv2 / numpy needed — cv2 and numpy are
stubbed so the module can be imported and its pure geometry + state machines
exercised anywhere Python 3 runs.

Usage (from repo root):
    cd windows_agent
    python test_jewelry.py

Exit code 0 = all pass, 1 = at least one failure.
"""
import sys
import types
import pathlib

# ── Stub cv2 + numpy so agent/jewelry.py imports without the ML stack ───────
class _Buf:
    def tobytes(self):
        return b"\xff\xd8"

class FakeMask:
    def __init__(self, on, total=100):
        self.on = on
        self.size = total

_FILLS = iter([])

def set_fills(seq):
    global _FILLS
    _FILLS = iter(seq)

def _mog2(**kw):
    def apply(roi):
        try:
            fill = next(_FILLS)
        except StopIteration:
            fill = 0.0
        return FakeMask(int(round(fill * 100)), 100)
    return types.SimpleNamespace(apply=apply)

cv2 = types.ModuleType("cv2")
cv2.IMWRITE_JPEG_QUALITY = 1
cv2.resize = lambda img, size: img
cv2.imencode = lambda *a, **k: (True, _Buf())
cv2.createBackgroundSubtractorMOG2 = _mog2
sys.modules["cv2"] = cv2

np = types.ModuleType("numpy")
np.count_nonzero = lambda m: int(m.on)
sys.modules["numpy"] = np

_AGENT_DIR = pathlib.Path(__file__).parent
sys.path.insert(0, str(_AGENT_DIR.parent))

from agent.jewelry import (  # noqa: E402
    point_in_polygon, parse_polygon, centroid, distance, _pixel_poly, _hand_points,
    JewelryHandoverDetector, JewelryTrayDetector, GrabAndRunDetector,
)


class FakeFrame:
    shape = (100, 100, 3)

    def __getitem__(self, key):
        return object()  # ROI content is irrelevant — the stub subtractor ignores it


def person(x, y, w, h, tid):
    p = types.SimpleNamespace(x=x, y=y, w=w, h=h, label="person", confidence=0.9, track_id=tid)
    p.to_dict = lambda: {"x": p.x, "y": p.y, "w": p.w, "h": p.h, "label": "person"}
    return p


results = []

def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name)


# ── Geometry ────────────────────────────────────────────────────────────────
sq = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]
check("point_in_polygon: inside", point_in_polygon(0.5, 0.5, sq) is True)
check("point_in_polygon: outside", point_in_polygon(0.05, 0.5, sq) is False)
check("point_in_polygon: None polygon is never inside", point_in_polygon(0.5, 0.5, None) is False)
check("point_in_polygon: degenerate polygon", point_in_polygon(0.5, 0.5, [(0, 0), (1, 0)]) is False)
check("parse_polygon: None -> None", parse_polygon(None) is None)
check("parse_polygon: <3 points -> None", parse_polygon([[0, 0], [1, 0]]) is None)
check("parse_polygon: valid", parse_polygon([[0, 0], [1, 0], [1, 1]]) == [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)])
check("distance", distance((0, 0), (3, 4)) == 5.0)
check("centroid", centroid((0, 0, 10, 20)) == (5.0, 10.0))
check("_pixel_poly: normalized -> pixels", _pixel_poly([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], 100, 50) == [(0.0, 0.0), (100.0, 0.0), (100.0, 50.0)])
hp = _hand_points((10, 20, 30, 40))
check("_hand_points: 5 candidates", len(hp) == 5 and (10, 40) in hp and (30, 40) in hp and (20, 40) in hp)

# ── Handover (reach-in -> withdraw) ─────────────────────────────────────────
check("handover: unconfigured -> never fires",
      JewelryHandoverDetector("cam", {}).configured is False)
h = JewelryHandoverDetector("cam", {
    "tray_polygon": [[0.4, 0.6], [0.6, 0.6], [0.6, 0.8], [0.4, 0.8]],
    "counter_polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    "min_hand_inside_frames": 2, "cooldown_seconds": 0, "require_person_at_counter": True,
})
f = FakeFrame()
check("handover: no event while hand stays inside", h.analyse([person(0.3, 0.2, 0.4, 0.5, 1)], f) is None)
check("handover: still no event on 2nd inside frame", h.analyse([person(0.3, 0.2, 0.4, 0.5, 1)], f) is None)
evt = h.analyse([person(0.3, 0.0, 0.4, 0.4, 1)], f)  # withdraw
check("handover: fires on withdraw", evt is not None and evt["event_type"] == "jewelry_handover")
check("handover: severity + track id", evt is not None and evt["severity"] == "high" and evt["metadata"]["person_track_id"] == 1)
check("handover: records frames_inside", evt is not None and evt["metadata"]["frames_inside"] == 2)

# ── Grab-and-run (case -> exit) ─────────────────────────────────────────────
check("grab_and_run: case-only config -> not configured",
      GrabAndRunDetector("cam", {"case_polygon": [[0, 0], [1, 0], [1, 1]]}).configured is False)
g = GrabAndRunDetector("cam", {
    "case_polygon": [[0.1, 0.1], [0.4, 0.1], [0.4, 0.9], [0.1, 0.9]],
    "exit_polygon": [[0.6, 0.1], [0.9, 0.1], [0.9, 0.9], [0.6, 0.9]],
    "max_window_seconds": 8.0, "min_exit_speed_px_s": 1.0, "cooldown_seconds": 0,
})
check("grab_and_run: no event while in case", g.analyse([person(0.15, 0.4, 0.2, 0.2, 2)], f) is None)
evt2 = g.analyse([person(0.7, 0.4, 0.2, 0.2, 2)], f)  # moved to exit
check("grab_and_run: fires on case->exit", evt2 is not None and evt2["event_type"] == "grab_and_run")
check("grab_and_run: severity critical", evt2 is not None and evt2["severity"] == "critical")
check("grab_and_run: records speed", evt2 is not None and evt2["metadata"]["exit_speed_px_s"] > 0)

# ── Tray change (foreground drop while person present) ──────────────────────
check("tray: no trays -> never fires", JewelryTrayDetector("cam", {}).configured is False)
set_fills([0.8, 0.4])
t = JewelryTrayDetector("cam", {
    "counter_polygon": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    "trays": [{"label": "Tray", "polygon": [[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6]]}],
    "drop_ratio_threshold": 0.25, "check_interval_seconds": 0.0, "cooldown_seconds": 0,
    "person_required": True,
})
check("tray: first observation is baseline (no event)", t.analyse([person(0.3, 0.3, 0.4, 0.4, 3)], f) is None)
evt3 = t.analyse([person(0.3, 0.3, 0.4, 0.4, 3)], f)  # fill 0.8 -> 0.4 = removal
check("tray: fires on removal", evt3 is not None and evt3["event_type"] == "jewelry_tray")
check("tray: removal severity high", evt3 is not None and evt3["severity"] == "high")
check("tray: change_type removed", evt3 is not None and evt3["metadata"]["change_type"] == "removed")

# person_required gate: nobody at the counter -> no event
set_fills([0.8, 0.4])
t2 = JewelryTrayDetector("cam", {
    "counter_polygon": [[0.0, 0.0], [0.2, 0.0], [0.2, 1.0], [0.0, 1.0]],  # far left
    "trays": [{"label": "Tray", "polygon": [[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6]]}],
    "drop_ratio_threshold": 0.25, "check_interval_seconds": 0.0, "cooldown_seconds": 0,
    "person_required": True,
})
check("tray: person gate blocks when nobody at counter", t2.analyse([person(0.7, 0.7, 0.2, 0.2, 4)], f) is None)

# ── Summary ─────────────────────────────────────────────────────────────────
failures = [n for n, ok in results if not ok]
print("\n%d passed, %d failed" % (len(results) - len(failures), len(failures)))
sys.exit(1 if failures else 0)
