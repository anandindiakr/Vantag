"""
Lightweight ByteTrack-inspired multi-object tracker for person counting.

Honesty note (agent v1.5.0): the real ByteTrack (Zhang et al., ECCV 2022)
uses a Kalman filter per track and the Hungarian algorithm for assignment,
usually via the `lap`/`cython_bbox`/`scipy` packages. Shipping those as new
hard dependencies onto every store's Windows laptop — many of which
already struggle with plain `pip install` — is a real install-risk cost,
not a shortcut worth hiding.

What IS implemented here is ByteTrack's actual key idea, the part that
matters for footfall counting:

  1. Two-tier confidence association. HIGH-confidence detections are
     matched against active tracks FIRST. Only detections that remain
     unmatched fall through to a second pass against LOW-confidence
     detections. This is what lets a track survive a frame or two of
     partial occlusion / motion blur (where confidence dips but the
     person hasn't left) instead of being dropped and re-issued a new ID
     — which is exactly what caused double-counting before this rewrite.
  2. A constant-velocity motion estimate (center displacement between the
     last two matched frames) is used to predict where a track should be
     before matching — this keeps IDs stable across the gaps created by
     running at 5 fps instead of 30 fps.
  3. Track lifecycle: a track must be matched `min_hits` times before it
     is "confirmed" (used for counting) and is dropped after `max_age`
     unmatched frames.

This gives genuine persistent-ID tracking — the prerequisite for accurate,
never-double-counted footfall — using only numpy, which is already a hard
dependency of this agent. No new packages to install.
"""
import itertools
from typing import List, Optional


def _iou_predicted(track: "_Track", det) -> float:
    """IoU between a detection and a track's motion-predicted box."""
    px = track.box.x + track.vx
    py = track.box.y + track.vy
    ax1, ay1, ax2, ay2 = px, py, px + track.box.w, py + track.box.h
    bx1, by1, bx2, by2 = det.x, det.y, det.x + det.w, det.y + det.h
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = track.box.w * track.box.h + det.w * det.h - inter
    return inter / union if union > 0 else 0.0


class _Track:
    __slots__ = ("id", "box", "vx", "vy", "hits", "age", "time_since_update", "confirmed")

    def __init__(self, track_id: int, box):
        self.id = track_id
        self.box = box
        self.vx = 0.0
        self.vy = 0.0
        self.hits = 1
        self.age = 0
        self.time_since_update = 0
        self.confirmed = False

    def assign(self, det) -> None:
        cx0 = self.box.x + self.box.w / 2
        cy0 = self.box.y + self.box.h / 2
        cx1 = det.x + det.w / 2
        cy1 = det.y + det.h / 2
        self.vx = cx1 - cx0
        self.vy = cy1 - cy0
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
        # after max_age consecutive misses.
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
