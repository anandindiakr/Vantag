from __future__ import annotations

import math
import time


def overlap(first, second) -> float:
    width = max(0, min(first.x + first.w, second.x + second.w) - max(first.x, second.x))
    height = max(0, min(first.y + first.h, second.y + second.h) - max(first.y, second.y))
    intersection = width * height
    return intersection / max(1e-9, first.w * first.h + second.w * second.h - intersection)


class PersonQuality:
    def __init__(self, pose, settings: dict):
        self.pose = pose
        self.mode = settings.get('mode', 'precision')
        self.confidence = float(settings.get('confidence', 0.6))
        self.confirmation_frames = int(settings.get('confirmation_frames', 3))
        self.status = {'mode': self.mode, 'confidence': self.confidence, 'confirmation_frames': self.confirmation_frames, 'evaluated_at': None, 'rejected_this_frame': 0, 'error': '', 'field_accuracy_verified': False}

    def filter(self, alert_boxes, count_boxes, frame):
        self.status.update(evaluated_at=time.time(), error='')
        candidates = [box for box in count_boxes if box.label == 'person' and box.confidence >= self.confidence and all(math.isfinite(value) for value in (box.x, box.y, box.w, box.h)) and box.w > 0 and box.h > 0]
        try:
            if self.mode == 'precision' and candidates:
                if self.pose is None:
                    raise RuntimeError('Person precision mode requires the bundled pose model; choose balanced mode explicitly if unavailable')
                poses = self.pose.detect_poses(frame, conf_threshold=0.4, raise_errors=True)
                supported = [person for person in poses if sum(float(point[2]) >= 0.35 for point in person.keypoints) >= 5 and any(person.kp(index, min_conf=0.35) is not None for index in (5, 6)) and any(person.kp(index, min_conf=0.35) is not None for index in (11, 12))]
                candidates = [box for box in candidates if any(overlap(box, person.box) >= 0.35 for person in supported)]
            self.status['rejected_this_frame'] = len(count_boxes) - len(candidates)
            return [box for box in alert_boxes if box.label != 'person' or box.confidence >= self.confidence and any(overlap(box, candidate) >= .5 for candidate in candidates)], candidates
        except Exception as exc:
            self.status['error'] = f'Person validation failed: {type(exc).__name__}'
            raise
