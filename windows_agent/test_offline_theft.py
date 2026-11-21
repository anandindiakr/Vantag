import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def concealment(center=0.49):
    from agent.inference import BoundingBox, PersonPose
    points = np.zeros((17, 3))
    for index, point in {5: (center - 0.03, 0.25), 6: (center + 0.03, 0.25), 11: (center - 0.03, 0.5), 12: (center + 0.03, 0.5), 9: (center, 0.55)}.items():
        points[index] = [*point, 0.9]
    return PersonPose(BoundingBox(center - 0.1, 0.1, 0.2, 0.6, 'person', 0.9), points)


def analyzer(pose, excluded=False):
    from agent.camera_worker import DetectionAnalyzer
    zones = [{'id': 'excluded', 'bbox': [0, 0, 1, 1]}] if excluded else []
    return DetectionAnalyzer('demo', pose_inference=pose, exclusion_zones=zones, detections={'shoplifting': True})


def test_pose_theft_respects_exclusions(monkeypatch):
    import agent.camera_worker as module
    detector = analyzer(SimpleNamespace(_session=object(), detect_poses=lambda *args, **kwargs: [concealment()]), excluded=True)
    for stamp in (100, 101.1, 102.2, 103.3):
        monkeypatch.setattr(module.time, 'time', lambda: stamp)
        assert not detector.analyse([], np.zeros((360, 640, 3), dtype=np.uint8))


def test_proximity_theft_already_respects_exclusions(monkeypatch):
    import agent.camera_worker as module
    from agent.inference import BoundingBox
    detector = analyzer(None, excluded=True)
    boxes = [concealment().box, BoundingBox(0.45, 0.3, 0.1, 0.1, 'backpack', 0.9)]
    for stamp in (100, 101, 102, 103):
        monkeypatch.setattr(module.time, 'time', lambda: stamp)
        assert not detector.analyse(boxes, np.zeros((360, 640, 3), dtype=np.uint8))


def test_concealment_survives_grid_boundary_and_marks_review(monkeypatch):
    import agent.camera_worker as module
    sample = [concealment()]
    detector = analyzer(SimpleNamespace(_session=object(), detect_poses=lambda *args, **kwargs: sample))
    events = []
    for stamp, center in ((100, 0.49), (101.1, 0.51), (102.2, 0.52)):
        sample[:] = [concealment(center)]
        monkeypatch.setattr(module.time, 'time', lambda: stamp)
        events.extend(detector.analyse([], np.zeros((360, 640, 3), dtype=np.uint8)))
    assert len(events) == 1
    assert events[0]['metadata']['requires_review'] is True
    assert events[0]['snapshot_b64']


def test_concealment_does_not_transfer_between_people(monkeypatch):
    import agent.camera_worker as module
    sample = []
    detector = analyzer(SimpleNamespace(_session=object(), detect_poses=lambda *args, **kwargs: sample))
    for stamp, center in ((100, 0.2), (101.1, 0.8), (102.2, 0.2)):
        sample[:] = [concealment(center)]
        monkeypatch.setattr(module.time, 'time', lambda: stamp)
        assert detector.analyse([], np.zeros((360, 640, 3), dtype=np.uint8)) == []


def test_ordinary_upright_pose_is_not_a_concealment_event(monkeypatch):
    import agent.camera_worker as module
    person = concealment()
    person.keypoints[9] = [0.35, 0.3, 0.9]
    detector = analyzer(SimpleNamespace(_session=object(), detect_poses=lambda *args, **kwargs: [person]))
    for stamp in (100, 101.1, 102.2, 103.3):
        monkeypatch.setattr(module.time, 'time', lambda: stamp)
        assert detector.analyse([], np.zeros((360, 640, 3), dtype=np.uint8)) == []


@pytest.mark.parametrize('posture', ['hanging_hand', 'horizontal', 'missing_shoulders'])
def test_non_concealment_posture_does_not_accumulate_a_theft_candidate(monkeypatch, posture):
    import agent.camera_worker as module
    person = concealment()
    if posture == 'hanging_hand':
        person.keypoints[9] = [0.49, 0.8, 0.9]
    elif posture == 'horizontal':
        person.keypoints[5] = [0.2, 0.48, 0.9]
        person.keypoints[6] = [0.2, 0.50, 0.9]
        person.keypoints[9] = [0.2, 0.55, 0.9]
    else:
        person.keypoints[5:7] = 0
    detector = analyzer(SimpleNamespace(_session=object(), detect_poses=lambda *args, **kwargs: [person]))
    for stamp in (100, 101.1, 102.2, 103.3):
        monkeypatch.setattr(module.time, 'time', lambda: stamp)
        assert detector.analyse([], np.zeros((360, 640, 3), dtype=np.uint8)) == []


def test_pose_error_is_visible_without_breaking_other_analytics():
    def fail(*args, **kwargs):
        raise RuntimeError('model failed')
    detector = analyzer(SimpleNamespace(_session=object(), detect_poses=fail))
    assert detector.analyse([], np.zeros((360, 640, 3), dtype=np.uint8)) == []
    assert 'RuntimeError' in detector._pose_detector.status['error']


def test_theft_and_inventory_status_explain_configuration(tmp_path):
    from agent.local.licensing import EntitlementStatus
    from agent.local.runtime import LocalRuntime, LocalSink
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    camera_id = store.save_camera({'name': 'Demo', 'rtsp_url': 'rtsp://192.168.1.102/102', 'detections': {'shoplifting': True, 'inventory_movement': True}})
    runtime = LocalRuntime.__new__(LocalRuntime)
    runtime.store, runtime.lock = store, threading.RLock()
    runtime.licence = SimpleNamespace(status=lambda: EntitlementStatus('active', claims={'features': ['shoplifting', 'inventory_movement']}))
    runtime.sink, runtime.detector, runtime.calibration, runtime.error = LocalSink(store), None, {}, ''
    runtime.workers = [SimpleNamespace(config=SimpleNamespace(id=camera_id, name='Demo'), is_connected=True, current_fps=1, inference_ms=1, inference_error='', count_sample=None)]
    status = runtime.status()['cameras'][0]
    assert 'shelf zone' in status['inventory_status']['state'].lower()
    assert 'pose' in status['theft_status']['state'].lower()
