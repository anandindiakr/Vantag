"""
proof_ai.py
===========
Self-contained PROOF that the Vantag AI pipeline performs REAL detection,
not demo/synthetic injection.

It:
  1. Loads the real YOLOv8 model (models/weights/yolov8n.pt) via YOLOEngine.
  2. Runs genuine inference on a real photo that contains several people.
  3. Feeds the real Detection objects into two of the production analyzers
     (RestrictedZone + QueueLength) and shows real events firing with
     real pixel coordinates and real person counts.

Run:  python proof_ai.py
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.inference.yolo_engine import YOLOEngine
from backend.analyzers.restricted_zone import RestrictedZoneDetector
from backend.analyzers.queue_length import QueueLengthAnalyzer

MODEL = os.path.join("models", "weights", "yolov8n.pt")


def get_test_image() -> np.ndarray:
    """Use ultralytics' bundled bus.jpg (has 4 people) if available, else download."""
    try:
        from ultralytics.utils import ASSETS
        p = os.path.join(str(ASSETS), "bus.jpg")
        if os.path.isfile(p):
            return cv2.imread(p)
    except Exception:
        pass
    # fallback: download a known image with people
    import urllib.request
    url = "https://ultralytics.com/images/bus.jpg"
    tmp = "test_people.jpg"
    urllib.request.urlretrieve(url, tmp)
    return cv2.imread(tmp)


def main() -> None:
    print("=" * 64)
    print("VANTAG AI PROOF  --  real YOLOv8 inference, no demo injection")
    print("=" * 64)

    frame = get_test_image()
    if frame is None:
        print("ERROR: could not obtain test image")
        sys.exit(1)
    h, w = frame.shape[:2]
    print(f"[1] Loaded real test image: {w}x{h} px")

    engine = YOLOEngine(MODEL, device="cpu", conf_threshold=0.4)
    dets = engine.detect(frame)
    persons = [d for d in dets if d.class_name == "person"]
    print(f"[2] YOLOv8 ran on the frame -> {len(dets)} objects, "
          f"{len(persons)} person(s)")
    for d in dets:
        print(f"      - {d.class_name:10s} conf={d.confidence:.2f} bbox={d.bbox}")

    if not persons:
        print("No persons detected -- cannot prove analyzers. Exiting.")
        sys.exit(1)

    # ---- Analyzer 1: RestrictedZone over the lower half of the frame --------
    poly = [[0, h // 2], [w, h // 2], [w, h], [0, h]]
    rz = RestrictedZoneDetector("cam-proof", {
        "restricted_zones": [{"name": "after-hours-floor", "polygon": poly,
                              "severity": "high"}],
        "min_frames_inside": 3,
        "cooldown_seconds": 0,
    })
    print("\n[3] RestrictedZone analyzer (real cv2 point-in-polygon):")
    zone_events = []
    for _ in range(3):  # needs 3 consecutive frames inside
        zone_events = rz.analyze(frame, dets, 0.0)
    if zone_events:
        for e in zone_events:
            print(f"    REAL EVENT -> zone='{e.zone_name}' person_track={e.person_track_id} "
                  f"conf={e.confidence:.2f} bbox={e.bbox} severity={e.severity}")
    else:
        print("    (no person foot-point fell inside the test polygon)")

    # ---- Analyzer 2: QueueLength counting real persons ---------------------
    ql = QueueLengthAnalyzer("cam-proof", {
        "queue_zones": [{"label": "checkout-1", "bbox": [0, 0, w, h], "max_queue": 1}],
        "check_interval_seconds": 0.0,
        "cooldown_seconds": 0,
    })
    print("\n[4] QueueLength analyzer (real person counting in zone):")
    q_events = ql.analyze(frame, dets, 0.0)
    if q_events:
        for e in q_events:
            print(f"    REAL EVENT -> zone='{e.zone_label}' queue_length={e.queue_length} "
                  f"(max_allowed={e.max_allowed}) severity={e.severity}")
    else:
        status = ql.get_queue_status()
        print(f"    counted {status}")

    print("\n" + "=" * 64)
    print("VERDICT: events above were produced from REAL YOLO detections on a")
    print("real photo -- counts/coordinates derive from the model, not templates.")
    print("=" * 64)


if __name__ == "__main__":
    main()
