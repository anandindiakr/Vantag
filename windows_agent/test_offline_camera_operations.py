import base64
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from test_offline_live_configuration import running_site, SampleWorker
from agent.local.licensing import EntitlementStatus
from agent.local.server import create_app


def client_for(store, runtime):
    client = TestClient(create_app(store, runtime.licence, runtime), base_url='http://127.0.0.1')
    client.post('/api/setup', json={'username': 'owner', 'password': 'unique-test-owner-password'})
    return client


def test_removing_one_camera_keeps_other_worker_and_cached_frame(running_site):
    store, runtime, first = running_site
    second = store.save_camera({'name': 'Second', 'rtsp_url': 'rtsp://viewer:pass@192.168.1.103/stream'})
    runtime.apply_camera(second)
    removed, survivor = runtime.workers
    runtime.sink.push_frame(second, base64.b64encode(b'surviving-frame').decode())
    with client_for(store, runtime) as client:
        response = client.request('DELETE', f'/api/cameras/{first}', json={})
    assert response.status_code == 200
    assert removed.stopped
    assert not survivor.stopped
    assert runtime.workers == [survivor]
    assert runtime.sink.frame(second)[0] == b'surviving-frame'
    assert len(store.cameras()) == 1


def test_saved_camera_test_uses_protected_connection_without_password_round_trip(running_site, monkeypatch):
    from agent import discovery
    store, runtime, first = running_site
    runtime.sink.push_frame(first, base64.b64encode(b'cached-frame').decode())
    monkeypatch.setattr(discovery, '_try_rtsp', lambda *args: pytest.fail('Already decoded stream must be reused'))
    with client_for(store, runtime) as client:
        response = client.post(f'/api/cameras/{first}/test', json={})
    assert response.status_code == 200
    assert response.json()['success']
    assert base64.b64decode(response.json()['thumbnail']) == b'cached-frame'
    assert 'pass' not in response.text
    assert 'rtsp://' not in response.text


def test_saved_camera_test_missing_camera_is_404_and_stays_authenticated(running_site):
    store, runtime, first = running_site
    with TestClient(create_app(store, runtime.licence, runtime), base_url='http://127.0.0.1') as client:
        assert client.post(f'/api/cameras/{first}/test', json={}).status_code == 401
    with client_for(store, runtime) as client:
        assert client.post('/api/cameras/missing/test', json={}).status_code == 404


def test_saved_camera_test_respects_entitlement(running_site):
    store, runtime, first = running_site
    runtime.licence = SimpleNamespace(status=lambda: EntitlementStatus('expired'))
    with client_for(store, runtime) as client:
        assert client.post(f'/api/cameras/{first}/test', json={}).status_code == 403


def test_eight_camera_workers_are_not_capped_at_two(running_site):
    store, runtime, first = running_site
    runtime.licence = SimpleNamespace(status=lambda: EntitlementStatus('active', claims={'camera_limit': 8, 'features': []}))
    initial = runtime.workers[0]
    for channel in range(2, 9):
        camera = store.save_camera({'name': f'Camera {channel}', 'rtsp_url': f'rtsp://viewer:pass@192.168.1.102/Streaming/Channels/{channel}02'})
        assert runtime.apply_camera(camera)
    assert len(runtime.workers) == 8
    assert runtime.workers[0] is initial
    assert not any(worker.stopped for worker in runtime.workers)


def test_status_requires_fresh_decoded_frame_and_reports_connection_reason(running_site):
    store, runtime, first = running_site
    worker = runtime.workers[0]
    worker.is_connected = True
    worker.current_fps = 12
    worker.inference_ms = 100
    worker.inference_error = ''
    worker.error_msg = 'No video frame decoded'
    worker.consecutive_failures = 2
    runtime.detector = SimpleNamespace(status={})
    runtime.sink.frames[first] = (b'expired-frame', time.time() - 20)
    status = runtime.status()
    assert status['cameras'][0]['connected'] is False
    assert status['cameras'][0]['connection_error'] == 'No video frame decoded'
    assert status['camera_capacity']['entitlement_limit'] == 3
    runtime.sink.push_frame(first, base64.b64encode(b'fresh-frame').decode())
    assert runtime.status()['cameras'][0]['connected'] is True
