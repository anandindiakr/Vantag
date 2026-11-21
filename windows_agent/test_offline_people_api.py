import base64
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
from agent.local.faces import LocalFaceEngine
from agent.local.people import LocalPeopleTools
from agent.local.server import create_app
from agent.local.store import SiteStore
from agent.inference import BoundingBox
from test_offline_people_tools import FaceFixture


@pytest.fixture
def site(tmp_path):
    store = SiteStore(tmp_path)
    licence = SimpleNamespace(status=lambda: SimpleNamespace(can_process=True, claims={'features': ['people_count']}))
    tools = LocalPeopleTools(store, licence, tmp_path / 'models', face_engine=FaceFixture())
    runtime = SimpleNamespace(people=tools)
    with TestClient(create_app(store, licence, runtime), base_url='http://127.0.0.1') as client:
        yield client, tools
    tools.close()


def login(client):
    assert client.post('/api/setup', json={'username': 'owner', 'password': 'test-only-private-password'}).status_code == 200


def test_api_is_authenticated_and_requires_authorisation(site):
    client, tools = site
    assert client.get('/api/people/staff').status_code == 401
    login(client)
    body = {'capture_enabled': True, 'recognition_enabled': False, 'retention_days': 7, 'authorised': False}
    assert client.post('/api/people/settings', json=body).status_code == 400
    body['authorised'] = True
    assert client.post('/api/people/settings', json=body).status_code == 200
    assert client.post('/api/people/settings', json={**body, 'retention_days': 31}).status_code == 422
    assert client.post('/api/people/settings', json=body, headers={'Origin': 'https://untrusted.invalid'}).status_code == 403


def test_staff_api_enrols_with_consent_hides_templates_and_revokes(site):
    client, tools = site
    login(client)
    body = {'name': 'Consenting operator', 'staff_code': 'A-1', 'consent': True, 'consent_note': 'Written consent recorded locally', 'photos': ['0-1', '0-2', '0-3']}
    assert client.post('/api/people/staff', json={**body, 'consent': False}).status_code == 400
    response = client.post('/api/people/staff', json=body)
    assert response.status_code == 200
    identifier = response.json()['id']
    assert 'templates' not in client.get('/api/people/staff').text
    assert client.request('DELETE', f'/api/people/staff/{identifier}', json={}).status_code == 200
    assert client.get('/api/people/staff').json() == []
    assert client.request('DELETE', f'/api/people/staff/{identifier}', json={}).status_code == 404


def test_observation_search_links_retention_and_expiry_api(site):
    client, tools = site
    login(client)
    tools.configure({'capture_enabled': True, 'authorised': True})
    box = BoundingBox(0, 0, 1, 1, 'person', .95)
    box.track_id = 7
    for camera in ('entrance', 'office'):
        tools.observe(camera, 'run', [box], np.full((160, 80, 3), 120, np.uint8))
    observations = client.get('/api/people/observations').json()
    assert observations['total'] == 2
    seed, target = observations['items']
    identifier = seed['id']
    assert 'descriptor' not in str(observations)
    assert client.get(f'/api/people/observations/{identifier}/thumbnail').content.startswith(b'\xff\xd8')
    assert client.get(f'/api/people/observations/{identifier}/candidates?minutes=0').status_code == 422
    candidates = client.get(f'/api/people/observations/{identifier}/candidates').json()
    assert candidates['items'][0]['id'] == target['id']
    assert candidates['identity_confirmed'] is False
    assert len(client.get(f'/api/people/observations/{identifier}/timeline').json()['items']) == 1
    linked = client.post(f'/api/people/observations/{identifier}/links', json={'target_id': target['id'], 'state': 'confirmed'})
    assert len(linked.json()['items']) == 2
    assert linked.json()['continuity_verified'] is False
    tools.licence.status = lambda: SimpleNamespace(can_process=False, claims={'features': ['people_count']})
    assert client.get('/api/people/observations').json()['total'] == 2
    assert client.post('/api/people/settings', json={'capture_enabled': True, 'authorised': True}).status_code == 400
    with tools.store.connect() as connection:
        connection.execute('UPDATE person_observations SET last_seen=?', (time.time() - 31 * 86400,))
    assert client.get(f'/api/people/observations/{identifier}/thumbnail').status_code == 404
    assert client.get('/api/people/observations').json()['total'] == 0


def test_invalid_photo_and_missing_models_are_actionable(tmp_path):
    engine = LocalFaceEngine(tmp_path)
    with pytest.raises(ValueError, match='valid JPG'):
        engine.template(base64.b64encode(b'not an image').decode())
    with pytest.raises(ValueError, match='unavailable'):
        engine.initialize()
    assert engine.status['available'] is False


def test_clearing_observations_keeps_staff_and_incident_archive(site):
    client, tools = site
    login(client)
    tools.store.record_event({'event_id': 'private-event', 'camera_id': 'office', 'event_type': 'fall_detected'})
    assert client.request('DELETE', '/api/people/observations', json={}).status_code == 200
    assert tools.store.events()[0]['event_id'] == 'private-event'


def test_worker_only_submits_confirmed_people_with_current_camera_policy(monkeypatch):
    from agent.local.worker import LocalCameraWorker
    from agent.camera_worker import CameraWorker
    monkeypatch.setattr(CameraWorker, '_run_inference', lambda self, frame: setattr(self, 'inference_error', ''))
    pending = []
    enabled = {'people_count': True}
    worker = LocalCameraWorker.__new__(LocalCameraWorker)
    worker._analyzer = SimpleNamespace(last_person_boxes=['confirmed'], _fall_detector=SimpleNamespace(reset=lambda: None))
    worker._detection_policy = lambda: enabled
    worker._people_observer = SimpleNamespace(submit=lambda *args: pending.append(args))
    worker._local_sink = SimpleNamespace(enabled=True)
    worker.config = SimpleNamespace(id='office')
    worker._local_run_id = 'session-1'
    worker._infer_inflight = SimpleNamespace(clear=lambda: None)
    worker._run_inference(np.zeros((80, 80, 3), np.uint8))
    assert pending[0][:3] == ('office', 'session-1', ['confirmed'])
    assert pending[0][-1]()
    enabled['people_count'] = False
    assert not pending[0][-1]()
