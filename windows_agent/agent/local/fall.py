from __future__ import annotations

import base64
import math
import time


class PoseFallDetector:
    def __init__(self, camera_id, pose, excluded=lambda box, frame: False):
        self.camera_id = camera_id
        self.pose = pose
        self.excluded = excluded
        self._tracks = []
        self._next_id = 1
        self._last_run = 0.0
        self.status = {"method": "pose_temporal_transition", "evaluated_at": None, "people_observed": 0, "error": "", "requires_review": True}

    def reset(self):
        self._tracks.clear()

    def analyse(self, persons, frame):
        current = time.monotonic()
        if current - self._last_run < 0.5:
            return None
        self._last_run = current
        try:
            if self.pose is None or self.pose._session is None:
                raise RuntimeError("Bundled pose model is unavailable")
            poses = self.pose.detect_poses(frame, conf_threshold=0.35, raise_errors=True)
            poses = [person for person in poses if not self.excluded(person.box, frame)]
            self.status["error"] = ""
            return self.observe(poses, frame, time.time())
        except Exception as exc:
            self.reset()
            self.status["error"] = f"Pose fall detection unavailable: {type(exc).__name__}"
            return None

    @staticmethod
    def _posture(person, frame):
        height, width = frame.shape[:2]
        shoulders = [point for index in (5, 6) if (point := person.kp(index, min_conf=0.35)) is not None]
        hips = [point for index in (11, 12) if (point := person.kp(index, min_conf=0.35)) is not None]
        if not shoulders or not hips:
            return False, False, None
        shoulder_x = sum(point[0] for point in shoulders) / len(shoulders)
        shoulder_y = sum(point[1] for point in shoulders) / len(shoulders)
        hip_x = sum(point[0] for point in hips) / len(hips)
        hip_y = sum(point[1] for point in hips) / len(hips)
        delta_x, delta_y = abs(hip_x - shoulder_x) * width, (hip_y - shoulder_y) * height
        if math.hypot(delta_x, delta_y) < min(width, height) * 0.025:
            return False, False, None
        ratio = person.box.h * height / max(1, person.box.w * width)
        upright = delta_y > delta_x * 1.3 and ratio >= 1.05
        horizontal = delta_x > abs(delta_y) * 1.5 and ratio <= 0.9
        return upright, horizontal, ratio

    @staticmethod
    def _association(track, box):
        previous = track["box"]
        center_distance = math.hypot(previous.x + previous.w / 2 - box.x - box.w / 2, previous.y + previous.h / 2 - box.y - box.h / 2)
        overlap_width = max(0, min(previous.x + previous.w, box.x + box.w) - max(previous.x, box.x))
        overlap_height = max(0, min(previous.y + previous.h, box.y + box.h) - max(previous.y, box.y))
        intersection = overlap_width * overlap_height
        union = previous.w * previous.h + box.w * box.h - intersection
        overlap = intersection / max(1e-6, union)
        if center_distance > 0.3 or (overlap < 0.05 and center_distance > 0.1):
            return -1
        return overlap + 1 - center_distance

    def observe(self, poses, frame, now):
        self.status.update(evaluated_at=now, people_observed=len(poses))
        self._tracks = [track for track in self._tracks if now - track["last_seen"] <= 3]
        unmatched = list(self._tracks)
        event = None
        for person in poses:
            if person.box.confidence < 0.35:
                continue
            candidates = [(self._association(track, person.box), track) for track in unmatched]
            score, track = max(candidates, key=lambda pair: pair[0]) if candidates else (-1, None)
            if score < 0:
                track = {"id": self._next_id, "upright_at": None, "upright_hits": 0, "fallen_since": None, "fallen_hits": 0, "last_event": 0}
                self._next_id += 1
                self._tracks.append(track)
            else:
                unmatched.remove(track)
            track.update(box=person.box, last_seen=now)
            upright, horizontal, ratio = self._posture(person, frame)
            if upright:
                track["upright_hits"] += 1
                track["upright_at"] = now
            if not horizontal:
                track.update(fallen_since=None, fallen_hits=0)
                continue
            if track["fallen_since"] is None:
                track["fallen_since"] = now
            track["fallen_hits"] += 1
            if track["upright_hits"] < 2 or track["upright_at"] is None or now - track["upright_at"] > 8:
                continue
            if track["fallen_hits"] < 3 or now - track["fallen_since"] < 1 or now - track["last_event"] < 60:
                continue
            if event is None:
                event = self._event(person, frame, now, ratio, track)
                track["last_event"] = now
        return event

    def _event(self, person, frame, now, ratio, track):
        import cv2
        height, width = frame.shape[:2]
        annotated = frame.copy()
        box = person.box
        left, top = max(0, int(box.x * width)), max(0, int(box.y * height))
        right, bottom = min(width - 1, int((box.x + box.w) * width)), min(height - 1, int((box.y + box.h) * height))
        cv2.rectangle(annotated, (left, top), (right, bottom), (0, 180, 255), 2)
        cv2.putText(annotated, "Possible fall - review required", (left, max(20, top - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 180, 255), 1, cv2.LINE_AA)
        scale = min(1, 960 / width)
        annotated = cv2.resize(annotated, (int(width * scale), int(height * scale)))
        success, encoded = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not success:
            raise ValueError("Fall evidence could not be encoded")
        return {"camera_id": self.camera_id, "event_type": "fall_detected", "severity": "high", "confidence": round(person.box.confidence, 3), "snapshot_b64": base64.b64encode(encoded).decode('ascii'), "metadata": {"timestamp": int(now * 1000), "detection_method": "pose_temporal_transition", "requires_review": True, "track_id": track["id"], "pixel_aspect_ratio": round(ratio, 3), "horizontal_samples": track["fallen_hits"], "person_pose": person.to_dict(), "description": "Possible fall: observed upright-to-horizontal body posture. Operator review required; not a medical diagnosis."}}
