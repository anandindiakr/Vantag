import base64
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


class SampleWorker:
    def __init__(self, camera):
        self.config = SimpleNamespace(**camera)
        self.count_sample = None
        self.stopped = False
        self.started = False
        self._local_sink = SimpleNamespace(enabled=True)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


@pytest.fixture
def running_site(tmp_path):
    from agent.local.licensing import EntitlementStatus
    from agent.local.runtime import LocalRuntime, LocalSink
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    first = store.save_camera({'name': 'First', 'rtsp_url': 'rtsp://viewer:pass%23@192.168.1.102:554/Streaming/Channels/102'})
    runtime = LocalRuntime.__new__(LocalRuntime)
    runtime.store = store
    runtime.licence = SimpleNamespace(status=lambda: EntitlementStatus('active', claims={'camera_limit': 3, 'features': ['people_count']}))
    runtime.lock = threading.RLock()
    runtime.sink = LocalSink(store)
    runtime.error = ''
    runtime.calibration = {'inference_ms': 100}
    runtime.detector = object()
    runtime.workers = [SampleWorker(store.cameras(include_secrets=True)[0])]
    runtime._make_worker = lambda camera, fps: SampleWorker(camera)
    return store, runtime, first


def test_adding_camera_keeps_existing_worker_and_preview(running_site):
    store, runtime, first = running_site
    original = runtime.workers[0]
    runtime.sink.push_frame(first, base64.b64encode(b'original-frame').decode())
    second = store.save_camera({'name': 'Second', 'rtsp_url': 'rtsp://viewer:pass%23@192.168.1.102:554/Streaming/Channels/202'})
    assert runtime.apply_camera(second)
    assert runtime.workers[0] is original
    assert not original.stopped
    assert runtime.workers[1].started
    assert runtime.sink.frame(first)[0] == b'original-frame'
    assert runtime.workers[1].config.rtsp_url.endswith('/202')


def test_hot_add_rebalances_existing_camera_inference_budget(running_site):
    store, runtime, first = running_site
    runtime.calibration = {'inference_ms': 400}
    original = runtime.workers[0]
    second = store.save_camera({'name': 'Second', 'rtsp_url': 'rtsp://192.168.1.102/202'})
    runtime.apply_camera(second)
    assert runtime.workers[0] is original
    assert all(worker._target_fps == 0.75 for worker in runtime.workers)
    assert not original.stopped


def test_saved_zone_applies_to_only_changed_camera(running_site):
    store, runtime, first = running_site
    other = SampleWorker({'id': 'other', 'name': 'Other'})
    runtime.workers.append(other)
    original = runtime.workers[0]
    camera = store.cameras()[0]
    camera['inventory_zones'] = [{'id': 'shelf', 'bbox': [0.1, 0.2, 0.6, 0.8], 'normalized': True}]
    store.save_camera(camera)
    assert runtime.apply_camera(first)
    assert original.stopped
    assert not other.stopped
    replacement = next(worker for worker in runtime.workers if worker.config.id == first)
    assert replacement.started
    assert replacement.config.inventory_zones == camera['inventory_zones']


def test_save_does_not_start_deliberately_stopped_monitoring(running_site):
    store, runtime, first = running_site
    runtime.workers.clear()
    assert runtime.apply_camera(first) is False
    assert runtime.workers == []


def test_apply_failure_preserves_other_stream_and_reports_error(running_site):
    store, runtime, first = running_site
    original = runtime.workers[0]
    second = store.save_camera({'name': 'Second', 'rtsp_url': 'rtsp://viewer:pass@192.168.1.102:554/Streaming/Channels/202'})
    def broken_factory(camera, fps):
        raise ValueError('Worker construction failed')
    runtime._make_worker = broken_factory
    with pytest.raises(ValueError):
        runtime.apply_camera(second)
    assert runtime.workers == [original]
    assert not original.stopped
    assert runtime.error
    assert len(store.cameras()) == 2


def test_camera_api_returns_real_application_state(running_site):
    from fastapi.testclient import TestClient
    from agent.local.server import create_app
    store, runtime, first = running_site
    with TestClient(create_app(store, runtime.licence, runtime), base_url='http://127.0.0.1') as client:
        client.post('/api/setup', json={'username': 'owner', 'password': 'a-long-unique-password'})
        response = client.post('/api/cameras', json={'name': 'Second', 'rtsp_url': 'rtsp://viewer:pass%23@192.168.1.102:554/Streaming/Channels/202'})
        assert response.status_code == 200
        assert response.json()['applied'] is True
        assert len(runtime.workers) == 2


def test_probe_reuses_fresh_matching_stream_without_second_connection(running_site, monkeypatch):
    from fastapi.testclient import TestClient
    from agent.local.server import create_app
    from agent import discovery
    store, runtime, first = running_site
    runtime.sink.push_frame(first, base64.b64encode(b'original-frame').decode())
    def unexpected_probe(*args, **kwargs):
        pytest.fail('An already decoded stream must not open another NVR connection')
    monkeypatch.setattr(discovery, '_try_rtsp', unexpected_probe)
    with TestClient(create_app(store, runtime.licence, runtime), base_url='http://127.0.0.1') as client:
        client.post('/api/setup', json={'username': 'owner', 'password': 'a-long-unique-password'})
        response = client.post('/api/probe', json={'rtsp_url': store.cameras(include_secrets=True)[0]['rtsp_url']})
        assert response.status_code == 200
        assert response.json()['success'] is True
        assert base64.b64decode(response.json()['thumbnail']) == b'original-frame'
