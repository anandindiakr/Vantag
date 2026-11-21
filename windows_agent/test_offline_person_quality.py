import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from agent.inference import BoundingBox, PersonPose
from agent.tracker import ByteTracker
from agent.local.person_quality import PersonQuality


def person(confidence=0.85):
    return BoundingBox(0.2, 0.1, 0.4, 0.7, 'person', confidence)


def seated_pose():
    points = np.array([[0.3 + (index % 2) * 0.1, 0.2 + index * 0.02, 0.9] for index in range(17)], dtype=np.float32)
    return PersonPose(person(), points)


def test_chair_false_person_without_human_landmarks_is_rejected():
    pose = SimpleNamespace(detect_poses=lambda *args, **kwargs: [])
    quality = PersonQuality(pose, {})
    accepted, _ = quality.filter([person()], [person()], np.zeros((480, 640, 3), np.uint8))
    assert accepted == []
    assert quality.status['rejected_this_frame'] == 1


def test_seated_stationary_person_does_not_require_motion_or_upright_shape():
    pose = SimpleNamespace(detect_poses=lambda *args, **kwargs: [seated_pose()])
    quality = PersonQuality(pose, {})
    tracker = ByteTracker(high_conf_threshold=quality.confidence, min_hits=quality.confirmation_frames)
    for index in range(4):
        box = person()
        _, accepted = quality.filter([box], [box], np.zeros((480, 640, 3), np.uint8))
        tracked = tracker.update(accepted)
        assert len([box for box in tracked if box.track_confirmed]) == int(index >= 2)


def test_configured_confirmation_frames_are_actually_honoured():
    tracker = ByteTracker(min_hits=4)
    for index in range(5):
        assert tracker.update([person()])[0].track_confirmed is (index >= 3)


def test_precision_mode_fails_visibly_without_pose_instead_of_silently_disabling_validation():
    quality = PersonQuality(None, {'mode': 'precision'})
    with pytest.raises(RuntimeError, match='pose'):
        quality.filter([person()], [person()], np.zeros((480, 640, 3), np.uint8))


def test_balanced_mode_uses_camera_confidence_but_does_not_claim_pose_verification():
    quality = PersonQuality(None, {'mode': 'balanced', 'confidence': 0.8, 'confirmation_frames': 4})
    _, accepted = quality.filter([person(0.7), person(0.9)], [person(0.7), person(0.9)], np.zeros((480, 640, 3), np.uint8))
    assert [box.confidence for box in accepted] == [0.9]
    assert quality.status['mode'] == 'balanced'
