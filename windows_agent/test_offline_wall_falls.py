import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_configuration_saving_is_not_limited_by_processing_entitlement(tmp_path):
    from fastapi.testclient import TestClient
    from agent.local.licensing import EntitlementStatus
    from agent.local.server import create_app
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    licence = SimpleNamespace(status=lambda: EntitlementStatus('active', claims={'camera_limit': 1, 'features': []}))
    with TestClient(create_app(store, licence, None), base_url='http://127.0.0.1') as client:
        client.post('/api/setup', json={'username': 'owner', 'password': 'a-long-unique-password'})
        for channel in range(1, 6):
            response = client.post('/api/cameras', json={'name': f'Camera {channel}', 'rtsp_url': f'rtsp://viewer:pass%23@192.168.1.102:554/Streaming/Channels/{channel}02'})
            assert response.status_code == 200
        response = client.get('/api/cameras')
        assert len(response.json()) == 5
        assert "img-src 'self' data: blob:" in response.headers['content-security-policy']


def test_start_capacity_validation_does_not_stop_existing_cameras(tmp_path):
    from agent.local.licensing import EntitlementStatus
    from agent.local.runtime import LocalRuntime
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    for channel in range(1, 3):
        store.save_camera({'name': str(channel), 'rtsp_url': f'rtsp://192.168.1.102/{channel}', 'enabled': True})
    runtime = LocalRuntime.__new__(LocalRuntime)
    runtime.store = store
    runtime.lock = threading.RLock()
    runtime.licence = SimpleNamespace(status=lambda: EntitlementStatus('active', claims={'camera_limit': 1}))
    stopped = []
    runtime._stop_workers = lambda: stopped.append(True)
    with pytest.raises(ValueError, match='[Cc]amera limit'):
        runtime.start()
    assert stopped == []


def make_pose(horizontal=False, center_x=0.3, center_y=0.4):
    import numpy as np
    from agent.inference import BoundingBox, PersonPose
    width, height = (0.30, 0.25) if horizontal else (0.12, 0.50)
    points = np.zeros((17, 3))
    if horizontal:
        points[5] = [center_x - 0.09, center_y - 0.03, 0.9]
        points[6] = [center_x - 0.09, center_y + 0.03, 0.9]
        points[11] = [center_x + 0.06, center_y - 0.03, 0.9]
        points[12] = [center_x + 0.06, center_y + 0.03, 0.9]
    else:
        points[5] = [center_x - 0.03, center_y - 0.15, 0.9]
        points[6] = [center_x + 0.03, center_y - 0.15, 0.9]
        points[11] = [center_x - 0.03, center_y + 0.05, 0.9]
        points[12] = [center_x + 0.03, center_y + 0.05, 0.9]
    return PersonPose(BoundingBox(center_x - width / 2, center_y - height / 2, width, height, 'person', 0.45), points)


def fall_sequence(detector, standing=True, excluded=False):
    import numpy as np
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    events = []
    samples = [(0.0, False, 0.3, 0.4), (0.5, False, 0.3, 0.4)] if standing else []
    samples += [(1.0, True, 0.4, 0.55), (1.5, True, 0.4, 0.55), (2.0, True, 0.4, 0.55), (2.5, True, 0.4, 0.55)]
    for stamp, horizontal, center_x, center_y in samples:
        pose = make_pose(horizontal, center_x, center_y)
        event = detector.observe([] if excluded else [pose], frame, now=100 + stamp)
        if event:
            events.append(event)
    return events


def test_pose_fall_survives_grid_boundary_and_lower_person_confidence():
    from agent.local.fall import PoseFallDetector
    detector = PoseFallDetector('pantry', None)
    events = fall_sequence(detector)
    assert len(events) == 1
    assert events[0]['event_type'] == 'fall_detected'
    assert events[0]['metadata']['detection_method'] == 'pose_temporal_transition'
    assert events[0]['metadata']['requires_review'] is True
    assert events[0]['snapshot_b64']
    assert detector.status['evaluated_at'] == 102.5


def test_already_lying_person_is_not_claimed_as_observed_fall():
    from agent.local.fall import PoseFallDetector
    assert fall_sequence(PoseFallDetector('pantry', None), standing=False) == []


def test_fall_history_expires_across_missing_frames():
    import numpy as np
    from agent.local.fall import PoseFallDetector
    detector = PoseFallDetector('pantry', None)
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    detector.observe([make_pose()], frame, now=100)
    detector.observe([make_pose()], frame, now=100.5)
    events = [detector.observe([make_pose(True)], frame, now=stamp) for stamp in (110, 111, 112, 113)]
    assert not any(events)


def test_pose_failure_is_visible_instead_of_no_people():
    import numpy as np
    from agent.local.fall import PoseFallDetector
    def fail(*args, **kwargs):
        raise RuntimeError('pose unavailable')
    detector = PoseFallDetector('pantry', SimpleNamespace(_session=object(), detect_poses=fail))
    assert detector.analyse([], np.zeros((360, 640, 3), dtype=np.uint8)) is None
    assert 'RuntimeError' in detector.status['error']
    assert detector.status['evaluated_at'] is None


def test_worker_pose_candidate_is_persisted_with_evidence(tmp_path, monkeypatch):
    import numpy as np
    from agent.config import CameraConfig
    from agent.local.runtime import LocalSink
    from agent.local.store import SiteStore
    from agent.local.worker import LocalCameraWorker
    import agent.local.fall as fall
    store = SiteStore(tmp_path)
    camera_id = store.save_camera({'name': 'Pantry', 'rtsp_url': 'rtsp://192.168.1.102/102'})
    sample = [make_pose()]
    pose = SimpleNamespace(_session=object(), detect_poses=lambda *args, **kwargs: sample)
    worker = LocalCameraWorker(config=CameraConfig(id=camera_id, name='Pantry', rtsp_url='rtsp://192.168.1.102/102'), inference=SimpleNamespace(detect=lambda *args, **kwargs: []), api_client=LocalSink(store), pose_inference=pose, detections={'fall_detected': True}, detection_policy=lambda: {'fall_detected': True})
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    try:
        for index in range(5):
            monkeypatch.setattr(fall.time, 'monotonic', lambda: 100 + index * 0.6)
            monkeypatch.setattr(fall.time, 'time', lambda: 100 + index * 0.6)
            sample[:] = [make_pose(horizontal=index >= 2)]
            worker._run_inference(frame)
        assert not worker.inference_error
        events = store.events()
        assert len(events) == 1
        assert events[0]['event_type'] == 'fall_detected'
        assert events[0]['evidence']['snapshot_b64']
    finally:
        worker.stop()


def test_status_explains_fall_schedule_and_disabled_state(tmp_path):
    from agent.local.licensing import EntitlementStatus
    from agent.local.runtime import LocalRuntime, LocalSink
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    camera_id = store.save_camera({'name': 'Pantry', 'rtsp_url': 'rtsp://192.168.1.102/102', 'detections': {'fall_detected': True}, 'enabled': False})
    runtime = LocalRuntime.__new__(LocalRuntime)
    runtime.store, runtime.lock = store, threading.RLock()
    runtime.licence = SimpleNamespace(status=lambda: EntitlementStatus('active', claims={'features': ['fall_detected']}))
    runtime.sink, runtime.detector, runtime.calibration, runtime.error = LocalSink(store), None, {}, ''
    runtime.workers = [SimpleNamespace(config=SimpleNamespace(id=camera_id, name='Pantry'), is_connected=True, current_fps=1, inference_ms=1, inference_error='', count_sample=None)]
    assert 'camera disabled' in runtime.status()['cameras'][0]['fall_status']['state']
    camera = store.cameras()[0]
    camera['detections']['fall_detected'] = False
    store.save_camera(camera)
    assert runtime.status()['cameras'][0]['fall_status']['state'] == 'Off for this camera'
