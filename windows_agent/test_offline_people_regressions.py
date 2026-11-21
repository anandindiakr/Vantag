import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from agent.camera_worker import DetectionAnalyzer
from agent.inference import BoundingBox
from agent.local.person_quality import PersonQuality
from agent.local.people import LocalPeopleTools
from agent.local.storage import export_backup, restore_backup
from agent.local.store import SiteStore
from test_offline_people_tools import FaceFixture


def test_separate_count_and_alert_boxes_keep_confirmed_restricted_zone_detection():
    frame = np.zeros((180, 320, 3), np.uint8)
    zone = {'id': 'secure', 'bbox': [.1, .1, .9, .9], 'normalized': True}
    analyzer = DetectionAnalyzer('office', restricted_zones=[zone], detections={'restricted_zone': True})
    analyzer._person_quality = PersonQuality(None, {'mode': 'balanced'})
    analyzer._tracker.min_hits = 3
    results = []
    for _ in range(3):
        alert_box = BoundingBox(.2, .2, .3, .6, 'person', .9)
        count_box = BoundingBox(.21, .2, .3, .6, 'person', .9)
        results.append(analyzer.analyse([alert_box], frame, [count_box]))
    assert results[:2] == [[], []]
    assert results[2][0]['event_type'] == 'restricted_zone'
    assert analyzer.last_person_count == 1


def test_private_backup_restores_staff_observations_links_and_incident_reviews(tmp_path):
    source = SiteStore(tmp_path / 'source')
    target = SiteStore(tmp_path / 'target')
    licence = SimpleNamespace(status=lambda: SimpleNamespace(can_process=True, claims={'features': ['people_count']}))
    tools = LocalPeopleTools(source, licence, tmp_path, face_engine=FaceFixture())
    target_tools = LocalPeopleTools(target, licence, tmp_path, face_engine=FaceFixture())
    try:
        tools.enrol({'staff_code': 'A-1', 'name': 'Consenting staff', 'consent': True, 'consent_note': 'Local written consent', 'photos': ['0-1', '0-2', '0-3']})
        tools.configure({'capture_enabled': True, 'authorised': True})
        for camera in ('entrance', 'office'):
            box = BoundingBox(0, 0, 1, 1, 'person', .9)
            box.track_id = 7
            tools.observe(camera, 'run', [box], np.full((160, 80, 3), 120, np.uint8))
        seed, match = tools.observations()['items']
        tools.review_link(seed['id'], match['id'], 'confirmed')
        source.record_event({'event_id': 'e1', 'event_type': 'fall_detected', 'camera_id': 'office'})
        with source.connect() as connection:
            connection.execute("INSERT INTO incident_reviews VALUES ('e1','confirmed','Reviewed locally',123)")
        backup = tmp_path / 'private.zip'
        export_backup(source, backup)
        restore_backup(target, backup)
        assert len(target_tools.staff()) == 1
        assert target_tools.observations()['total'] == 2
        assert target_tools.thumbnail(seed['id']).startswith(b'\xff\xd8')
        assert len(target_tools.timeline(seed['id'])['items']) == 2
        assert target.incident_search()['items'][0]['review']['state'] == 'confirmed'
    finally:
        tools.close()
        target_tools.close()
