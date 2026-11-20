import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.mark.parametrize(('path', 'channel', 'stream'), [('/Streaming/Channels/402', 4, 'Substream'), ('/Streaming/Channels/1201', 12, 'Main'), ('/Streaming/Channels/6402', 64, 'Substream'), ('/cam/realmonitor?channel=5&subtype=1', 5, 'Substream'), ('/custom', None, 'Custom')])
def test_identity_does_not_expose_credentials(path, channel, stream):
    from agent.local.store import stream_identity
    identity = stream_identity('rtsp://owner:private%23@192.168.50.79:554' + path)
    assert identity['channel'] == channel
    assert identity['stream_type'] == stream
    assert identity['host'] == '192.168.50.79'
    assert 'private' not in str(identity)
    assert 'owner' not in str(identity)


def test_duplicate_channel_is_rejected_across_main_and_substreams(tmp_path):
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    camera_id = store.save_camera({'name': 'Original', 'rtsp_url': 'rtsp://viewer:pass%23@192.168.50.79/Streaming/Channels/402'})
    with pytest.raises(ValueError, match='already saved'):
        store.save_camera({'name': 'Duplicate', 'rtsp_url': 'rtsp://other:another@192.168.50.79:554/Streaming/Channels/401'})
    assert len(store.cameras()) == 1
    store.save_camera({'id': camera_id, 'name': 'Updated', 'rtsp_url': 'rtsp://viewer:pass%23@192.168.50.79/Streaming/Channels/401'})
    store.save_camera({'name': 'Other device', 'rtsp_url': 'rtsp://viewer:pass%23@192.168.50.84/Streaming/Channels/401'})
    assert len(store.cameras()) == 2


def test_camera_api_exposes_identity_and_keeps_zone_saves_compatible(tmp_path):
    from fastapi.testclient import TestClient
    from agent.local.licensing import EntitlementStatus
    from agent.local.server import create_app
    from agent.local.store import SiteStore
    store = SiteStore(tmp_path)
    licence = SimpleNamespace(status=lambda: EntitlementStatus('active', claims={'camera_limit': 8, 'features': []}))
    with TestClient(create_app(store, licence, None), base_url='http://127.0.0.1') as client:
        client.post('/api/setup', json={'username': 'owner', 'password': 'a-long-unique-password'})
        payload = {'name': 'Camera 5', 'rtsp_url': 'rtsp://viewer:private%23@192.168.50.84/Streaming/Channels/502'}
        assert client.post('/api/cameras', json=payload).status_code == 200
        camera = client.get('/api/cameras').json()[0]
        assert camera.pop('stream_info')['channel'] == 5
        assert 'private' not in str(camera)
        assert 'rtsp_url' not in camera
        camera['inventory_zones'] = [{'bbox': [0.1, 0.1, 0.5, 0.5]}]
        assert client.post('/api/cameras', json=camera).status_code == 200
        duplicate = client.post('/api/cameras', json={**payload, 'name': 'Duplicate'})
        assert duplicate.status_code == 400
        assert 'already saved' in duplicate.json()['detail']
        assert client.get('/api/cameras').json()[0]['inventory_zones']
