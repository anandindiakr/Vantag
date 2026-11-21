import collections
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from agent import camera_worker
from agent.inference import BoundingBox
from test_offline_live_configuration import running_site
from test_offline_camera_operations import client_for


FRAME = np.zeros((180, 320, 3), dtype=np.uint8)
ZONE = {'id': 'secure', 'label': 'Staff only', 'bbox': [0.5, 0.2, 0.9, 0.9], 'normalized': True}


def person(x=0.55, y=0.3):
    return BoundingBox(x=x, y=y, w=0.1, h=0.3, label='person', confidence=0.9)


def test_restricted_zones_save_and_round_trip_via_authenticated_api(running_site):
    store, runtime, first = running_site
    camera = store.cameras()[0]
    camera.pop('stream_info', None)
    camera['restricted_zones'] = [ZONE]
    with client_for(store, runtime) as client:
        response = client.post('/api/cameras', json=camera)
        assert response.status_code == 200
        assert response.json()['applied']
        saved = client.get('/api/cameras').json()[0]
        assert saved['restricted_zones'] == [ZONE]
        camera['restricted_zones'] = [{'id': 'bad', 'bbox': [0.9, 0.2, 0.1, 0.9]}]
        assert client.post('/api/cameras', json=camera).status_code == 400
    assert store.cameras()[0]['restricted_zones'] == [ZONE]


def test_restricted_zone_rearms_after_exit_but_obeys_cooldown(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(camera_worker.time, 'time', lambda: now[0])
    analyzer = camera_worker.DetectionAnalyzer('cam', restricted_zones=[ZONE], detections={'restricted_zone': True})
    assert len(analyzer.analyse([person()], FRAME)) == 1
    analyzer.analyse([], FRAME)
    now[0] += 61
    assert len(analyzer.analyse([person()], FRAME)) == 1


def test_restricted_zone_alerts_on_entry_not_thirty_second_stationary_dwell():
    analyzer = camera_worker.DetectionAnalyzer('cam', restricted_zones=[ZONE], detections={'restricted_zone': True})
    assert not analyzer.analyse([person(0.1)], FRAME)
    events = analyzer.analyse([person()], FRAME)
    assert [event['event_type'] for event in events] == ['restricted_zone']
    assert events[0]['metadata']['zone_id'] == 'secure'
    assert events[0]['metadata']['method'] == 'person_center_zone_entry'
    assert not analyzer.analyse([person()], FRAME)


@pytest.mark.parametrize('zones,enabled,mask', [([], True, []), ([ZONE], False, []), ([ZONE], True, [ZONE])])
def test_restricted_zone_no_alert_without_zone_optin_or_inside_mask(zones, enabled, mask):
    analyzer = camera_worker.DetectionAnalyzer('cam', restricted_zones=zones, detections={'restricted_zone': enabled}, exclusion_zones=mask)
    for _ in range(160):
        assert not analyzer.analyse([person()], FRAME)


def test_crowding_positive_negative_and_reset(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(camera_worker.time, 'time', lambda: now[0])
    detector = camera_worker.CrowdDetector('cam')
    assert detector.analyse([person()] * 4, FRAME) is None
    assert detector.analyse([person()] * 6, FRAME) is None
    now[0] += 6
    assert detector.analyse([person()] * 6, FRAME)['event_type'] == 'crowding'
    assert detector.analyse([], FRAME) is None
    assert detector._crowd_since is None


def test_loitering_requires_motion_and_elapsed_time(monkeypatch):
    monkeypatch.setattr(camera_worker.time, 'time', lambda: 200.0)
    detector = camera_worker.LoiteringDetector('cam')
    subject = person(0.45, 0.35)
    assert detector.analyse([subject], FRAME) is None
    detector._zones['1_1'] = {'first_seen': 100, 'positions': collections.deque([(0.44 + i * 0.005, 0.47 + i * 0.003) for i in range(30)], maxlen=50), 'last_event': 0}
    assert detector.analyse([subject], FRAME)['event_type'] == 'loitering'
    assert detector.analyse([], FRAME) is None
    assert not detector._zones


def test_pacing_candidate_does_not_fire_for_straight_motion():
    detector = camera_worker.SuspiciousBehaviorDetector('cam')
    assert all(detector.analyse([person(0.50 + index * 0.006, 0.5)], FRAME) is None for index in range(22))
    detector = camera_worker.SuspiciousBehaviorDetector('cam')
    events = [detector.analyse([person(0.65 if index % 2 else 0.5, 0.5)], FRAME) for index in range(22)]
    assert any(event and event['event_type'] == 'suspicious_behavior' for event in events)


def test_visible_count_is_not_invented_from_empty_or_masked_frames():
    analyzer = camera_worker.DetectionAnalyzer('cam', detections={'people_count': True}, exclusion_zones=[ZONE])
    analyzer.analyse([person()], FRAME)
    assert analyzer.last_person_count == 0
    analyzer.analyse([], FRAME)
    assert analyzer.last_person_count == 0
