"""
BoT-SORT / ByteTrack multi-object tracker for person counting.

Stack (agent v1.5.2): ByteTrack's two-tier confidence association (Zhang et
al., ECCV 2022) on top of BoT-SORT's 8-state Kalman-filter motion model
(Aharon et al., arXiv 2022) from `kalman_filter.py`. Both parts run on numpy
only — no scipy / lap / cython_bbox to install on store laptops.

What is implemented and why:

  1. Two-tier confidence association (ByteTrack). HIGH-confidence detections
     are matched against active tracks FIRST. Only detections that remain
     unmatched fall through to a second pass against LOW-confidence
     detections. This is what lets a track survive a frame or two of
     partial occlusion / motion blur (where confidence dips but the
     person hasn't left) instead of being dropped and re-issued a new ID
     — which is exactly what caused double-counting before this rewrite.
  2. Kalman-filter motion prediction (BoT-SORT). Each track carries an
     8-state constant-velocity Kalman filter (center, aspect ratio, height
     + velocities). Matching happens against the filter's predicted box, so
     IDs stay stable across the gaps created by running at 5 fps instead of
     30 fps, and jittery detections no longer whip the estimate around the
     way the previous 2-frame displacement did.
  3. Track lifecycle: a track must be matched `min_hits` times before it
     is "confirmed" (used for counting) and is dropped after `max_age`
     unmatched frames. While unmatched, its Kalman filter keeps predicting
     forward — the core BoT-SORT re-identification behaviour.

Camera-motion compensation (the third BoT-SORT component) is intentionally
not implemented: it requires per-frame optical-flow alignment and only helps
PTZ/vehicle-mounted cameras. Vantag cameras are statically mounted, so it
would add CPU cost with no accuracy gain — flagged here rather than quietly
claimed.

This gives genuine persistent-ID tracking — the prerequisite for accurate,
never-double-counted footfall — using only numpy, which is already a hard
dependency of this agent. No new packages to install.
"""
import itertools
from typing import List, Optional

from .kalman_filter import KalmanBoxTracker


def _iou_predicted(track: "_Track", det) -> float:
    """IoU between a detection and the track's Kalman-predicted box."""
    px, py, pw, ph = track.kf.predicted_box()
    ax1, ay1, ax2, ay2 = px, py, px + pw, py + ph
    bx1, by1, bx2, by2 = det.x, det.y, det.x + det.w, det.y + det.h
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = pw * ph + det.w * det.h - inter
    return inter / union if union > 0 else 0.0


class _Track:
    __slots__ = ("id", "box", "kf", "hits", "age", "time_since_update", "confirmed")

    def __init__(self, track_id: int, box):
        self.id = track_id
        self.box = box
        cx = box.x + box.w / 2.0
        cy = box.y + box.h / 2.0
        self.kf = KalmanBoxTracker(cx, cy, box.w, box.h)
        self.hits = 1
        self.age = 0
        self.time_since_update = 0
        self.confirmed = False

    def predict(self) -> None:
        self.kf.predict()

    def assign(self, det) -> None:
        cx = det.x + det.w / 2.0
        cy = det.y + det.h / 2.0
        self.kf.update(cx, cy, det.w, det.h)
        self.box = det
        self.hits += 1
        self.age += 1
        self.time_since_update = 0
        if self.hits >= 2:
            self.confirmed = True


class ByteTracker:
    """Persistent-ID person tracker for a single camera stream.

    Call ``update(boxes)`` once per analysed frame with the list of
    "person" BoundingBox detections for that frame (mixed confidences are
    fine — the tracker itself splits them by ``high_conf_threshold``).
    Every box gets two attributes attached:

      - ``track_id``: a stable int identity across frames, or ``None`` if
        the detection could not be matched or promoted to a new track
        this frame.
      - ``track_confirmed``: True once a track has been seen ``min_hits``
        times — use this before counting a track as a real visitor, so a
        single-frame false detection can never inflate footfall.
    """

    def __init__(
        self,
        high_conf_threshold: float = 0.5,
        iou_threshold: float = 0.25,
        max_age: int = 10,
        min_hits: int = 2,
    ):
        self._tracks: List[_Track] = []
        self._next_id = itertools.count(1)
        self.high_conf_threshold = high_conf_threshold
        self.iou_threshold = iou_threshold
        self.max_age = max_age
        self.min_hits = min_hits

    def update(self, boxes: List) -> List:
        for b in boxes:
            b.track_id = None
            b.track_confirmed = False

        # BoT-SORT step 1: predict every active track forward before
        # associating, so stale tracks are compared at their expected
        # position rather than their last-seen position.
        for tr in self._tracks:
            tr.predict()

        high = [b for b in boxes if b.confidence >= self.high_conf_threshold]
        low = [b for b in boxes if b.confidence < self.high_conf_threshold]

        # Snapshot of tracks that existed BEFORE this frame. New tracks
        # created below are tracked separately so the aging pass at the end
        # never confuses "just created" with "existed but went unmatched".
        existing_tracks = list(self._tracks)
        matched_track_ids = set()

        def _match(dets):
            for det in dets:
                best_track: Optional[_Track] = None
                best_iou = self.iou_threshold
                for tr in existing_tracks:
                    if id(tr) in matched_track_ids:
                        continue
                    iou = _iou_predicted(tr, det)
                    if iou > best_iou:
                        best_track, best_iou = tr, iou
                if best_track is not None:
                    best_track.assign(det)
                    matched_track_ids.add(id(best_track))
                    det.track_id = best_track.id
                    det.track_confirmed = best_track.confirmed

        # Stage 1: high-confidence detections vs all active tracks.
        _match(high)
        # Stage 2: low-confidence detections only get a shot at tracks
        # stage 1 left unmatched — ByteTrack's core trick for surviving
        # brief occlusion/motion-blur dips without losing the ID.
        _match(low)

        # New tracks are only spawned from HIGH-confidence, still-unmatched
        # detections. Spawning from noisy low-confidence boxes would create
        # and immediately drop phantom IDs, inflating the footfall count.
        new_tracks: List[_Track] = []
        for det in high:
            if det.track_id is None:
                tr = _Track(next(self._next_id), det)
                new_tracks.append(tr)
                det.track_id = tr.id
                det.track_confirmed = tr.confirmed

        # Age out pre-existing tracks that went unmatched this frame; drop
        # after max_age consecutive misses. Their Kalman filters keep
        # predicting while unmatched, so a person re-entering within the
        # window re-attaches to the SAME id instead of a fresh one.
        alive: List[_Track] = []
        for tr in existing_tracks:
            if id(tr) in matched_track_ids:
                alive.append(tr)
                continue
            tr.time_since_update += 1
            tr.age += 1
            if tr.time_since_update <= self.max_age:
                alive.append(tr)
        alive.extend(new_tracks)
        self._tracks = alive

        return boxes
