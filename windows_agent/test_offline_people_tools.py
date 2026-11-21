import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from agent.local.people import LocalPeopleTools
from agent.local.store import SiteStore
from agent.inference import BoundingBox


class FaceFixture:
    status = {'available': True, 'model': 'fixture, not an accuracy test'}

    def template(self, photo):
        if photo == 'no-face':
            raise ValueError('Exactly one clear face is required')
        index = int(photo.split('-')[0])
        value = np.zeros(128, np.float32)
        value[index] = 1
        return value


@pytest.fixture
def people(tmp_path):
    store = SiteStore(tmp_path)
    licence = SimpleNamespace(status=lambda: SimpleNamespace(can_process=True, claims={'features': ['people_count']}))
    tools = LocalPeopleTools(store, licence, tmp_path / 'models', face_engine=FaceFixture())
    yield store, tools
    tools.close()


def enrol(tools, number=0):
    return tools.enrol({'name': f'Consenting staff {number}', 'staff_code': f'S-{number}', 'consent': True, 'consent_note': 'Written workplace consent recorded by owner', 'photos': [f'{number}-{index}' for index in range(3)]})


def test_staff_enrolment_requires_consent_and_encrypted_templates(people):
    store, tools = people
    with pytest.raises(ValueError, match='consent'):
        tools.enrol({'name': 'Someone', 'staff_code': 'S-0', 'consent': False, 'photos': ['0-1', '0-2', '0-3']})
    staff = enrol(tools)
    assert tools.staff()[0]['id'] == staff['id']
    assert 'templates' not in tools.staff()[0]
    with store.connect() as connection:
        protected = connection.execute('SELECT templates FROM staff_profiles').fetchone()[0]
    assert '[1.0,' not in protected
    with pytest.raises(ValueError, match='already'):
        enrol(tools)


def test_unknown_and_ambiguous_faces_are_not_forced_to_a_name(people):
    _, tools = people
    enrol(tools)
    assert tools.match_face('1-photo') is None
    assert tools.match_face('0-photo')['staff_id']
    second = enrol(tools, 1)
    with tools.store.connect() as connection:
        connection.execute('UPDATE staff_profiles SET templates=(SELECT templates FROM staff_profiles WHERE staff_code=?) WHERE id=?', ('S-0', second['id']))
    assert tools.match_face('0-photo') is None


def test_cross_camera_search_is_anonymous_reviewable_and_does_not_automatically_link(people):
    store, tools = people
    tools.configure({'capture_enabled': True, 'recognition_enabled': False, 'retention_days': 7, 'authorised': True})
    box = BoundingBox(0, 0, 1, 1, 'person', .95)
    box.track_id = 1
    red = np.zeros((160, 80, 3), np.uint8)
    red[:, :, 2] = 200
    blue = np.zeros_like(red)
    blue[:, :, 0] = 200
    tools.observe('entrance', 'run', [box], red, now=1000)
    tools.observe('office', 'run', [box], red, now=1010)
    tools.observe('pantry', 'run', [box], blue, now=1012)
    observations = tools.observations(now=1020)['items']
    seed = next(item for item in observations if item['camera_id'] == 'entrance')
    matches = tools.candidates(seed['id'], minutes=5, now=1020)
    assert matches['items'][0]['camera_id'] == 'office'
    assert matches['items'][0]['state'] == 'possible_appearance_match'
    assert 'name' not in json.dumps(matches)
    assert tools.timeline(seed['id'])['items'] == [seed]
    target = matches['items'][0]
    tools.review_link(seed['id'], target['id'], 'confirmed')
    assert len(tools.timeline(seed['id'])['items']) == 2
    tools.review_link(seed['id'], target['id'], 'rejected')
    assert len(tools.timeline(seed['id'])['items']) == 1
    assert 'descriptor' not in seed and 'thumbnail' not in seed
    assert tools.thumbnail(seed['id']).startswith(b'\xff\xd8')


def test_deleting_staff_removes_templates_and_named_sighting_links(people):
    store, tools = people
    staff = enrol(tools)
    with store.connect() as connection:
        connection.execute('INSERT INTO person_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', ('track', 'office', 'run', 1, 1000, 1001, 'protected', 'protected', staff['id'], .9))
    tools.delete_staff(staff['id'])
    assert tools.staff() == []
    with store.connect() as connection:
        assert connection.execute('SELECT staff_id FROM person_observations').fetchone()[0] is None
        assert connection.execute('SELECT COUNT(*) FROM staff_profiles').fetchone()[0] == 0


def test_capture_is_opt_in_and_retention_does_not_delete_incidents(people):
    store, tools = people
    box = BoundingBox(0, 0, 1, 1, 'person', .95)
    box.track_id = 1
    image = np.full((160, 80, 3), 120, np.uint8)
    tools.observe('office', 'run', [box], image, now=1000)
    assert tools.observations(now=1000)['items'] == []
    store.record_event({'event_id': 'retained-incident', 'event_type': 'fall_detected', 'camera_id': 'office'})
    tools.configure({'capture_enabled': True, 'recognition_enabled': False, 'retention_days': 1, 'authorised': True})
    tools.observe('office', 'run', [box], image, now=1000)
    assert tools.observations(now=1000)['total'] == 1
    assert tools.observations(now=1000 + 86401)['total'] == 0
    assert len(store.events()) == 1


def test_expiry_blocks_new_capture_but_preserves_saved_search_and_deletion(people):
    _, tools = people
    staff = enrol(tools)
    tools.licence.status = lambda: SimpleNamespace(can_process=False, claims={'features': ['people_count']})
    with pytest.raises(ValueError, match='entitlement'):
        enrol(tools, 1)
    with pytest.raises(ValueError, match='entitlement'):
        tools.configure({'capture_enabled': True, 'recognition_enabled': False, 'retention_days': 7, 'authorised': True})
    assert tools.observations()['items'] == []
    tools.delete_staff(staff['id'])
