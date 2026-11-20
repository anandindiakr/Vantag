import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from agent import discovery


@pytest.mark.parametrize('code,stage', [(401, 'credentials'), (403, 'permissions'), (None, 'protocol')])
def test_detection_stops_before_path_scan_or_decode_on_rejection(monkeypatch, code, stage):
    describe = Mock(return_value={'code': code, 'authenticated': True, 'brand_hint': None})
    decode = Mock()
    monkeypatch.setattr(discovery, '_describe_stream', describe, raising=False)
    monkeypatch.setattr(discovery, '_try_rtsp', decode)
    result = discovery.auto_diagnose_stream('rtsp://admin:literal%23@192.168.1.2:554/custom', channel=3)
    assert result['success'] is False
    assert result['failed_stage'] == stage
    assert describe.call_count == 1
    decode.assert_not_called()
    assert 'literal' not in str(result)


def test_detection_preserves_requested_channel_and_requires_decoded_frame(monkeypatch):
    paths = []

    def describe(url, timeout):
        paths.append(url)
        return {'code': 200 if '/cam/realmonitor?' in url else 404, 'authenticated': True, 'brand_hint': 'dahua'}

    monkeypatch.setattr(discovery, '_describe_stream', describe, raising=False)
    decode = Mock(return_value={'thumbnail': 'jpeg'})
    monkeypatch.setattr(discovery, '_try_rtsp', decode)
    result = discovery.auto_diagnose_stream('rtsp://admin:literal%23@192.168.1.2:554/wrong', channel=3)
    assert result['success'] is True
    assert result['path'] == '/cam/realmonitor?channel=3&subtype=1'
    assert result['brand_hint'] == 'dahua'
    assert all('channel=1&' not in url and '/101' not in url for url in paths)
    assert decode.call_args.args == ('192.168.1.2', 554, result['path'], 'admin', 'literal#')
    assert 'literal' not in str(result)


def test_description_without_video_is_not_success(monkeypatch):
    monkeypatch.setattr(discovery, '_describe_stream', Mock(return_value={'code': 200, 'authenticated': True, 'brand_hint': None}), raising=False)
    monkeypatch.setattr(discovery, '_try_rtsp', Mock(return_value=None))
    result = discovery.auto_diagnose_stream('rtsp://u:p@192.168.1.2:554/custom')
    assert result['failed_stage'] == 'decode'
    assert not result['success']
    assert result['path'] is None


def test_detection_bounds_unknown_channel_search(monkeypatch):
    describe = Mock(return_value={'code': 404, 'authenticated': False, 'brand_hint': None})
    monkeypatch.setattr(discovery, '_describe_stream', describe, raising=False)
    monkeypatch.setattr(discovery, '_try_rtsp', Mock())
    result = discovery.auto_diagnose_stream('rtsp://u:p@192.168.1.2:554/custom', channel=6)
    assert result['failed_stage'] == 'path'
    assert describe.call_count <= 10
    assert all('/stream1' not in call.args[0] and '/101' not in call.args[0] for call in describe.call_args_list)
    assert result['stages']['credentials'] == 'unconfirmed'


def test_detection_never_accepts_a_known_different_channel(monkeypatch):
    describe = Mock(return_value={'code': 200, 'authenticated': True, 'brand_hint': None})
    monkeypatch.setattr(discovery, '_describe_stream', describe)
    monkeypatch.setattr(discovery, '_try_rtsp', Mock(return_value={'thumbnail': 'jpeg'}))
    result = discovery.auto_diagnose_stream('rtsp://u:p@192.168.1.2/Streaming/Channels/102', channel=6)
    assert result['success']
    assert result['path'] == '/cam/realmonitor?channel=6&subtype=1'
    assert '/Streaming/Channels/102' not in describe.call_args.args[0]


def test_detection_reports_timeout_without_leaking_credentials(monkeypatch):
    monkeypatch.setattr(discovery, '_describe_stream', Mock(side_effect=TimeoutError()), raising=False)
    result = discovery.auto_diagnose_stream('rtsp://u:secret@192.168.1.2:554/custom')
    assert result['failed_stage'] == 'network'
    assert 'secret' not in str(result)


def test_auto_detect_endpoint_requires_auth_and_private_address(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from agent.local.server import create_app
    from agent.local.store import SiteStore

    store = SiteStore(tmp_path)
    store.create_owner('owner', 'test-only-owner-password')
    licence = SimpleNamespace(status=lambda: SimpleNamespace(can_process=True))
    client = TestClient(create_app(store, licence, None), base_url='http://127.0.0.1')
    assert client.post('/api/auto-detect', json={}).status_code == 401
    assert client.post('/api/login', json={'username': 'owner', 'password': 'test-only-owner-password'}).status_code == 200
    detect = Mock(return_value={'success': False, 'failed_stage': 'credentials'})
    monkeypatch.setattr(discovery, 'auto_diagnose_stream', detect, raising=False)
    assert client.post('/api/auto-detect', json={'rtsp_url': 'rtsp://u:p@8.8.8.8/path'}).status_code == 400
    detect.assert_not_called()
    assert client.post('/api/auto-detect', json={'rtsp_url': 'rtsp://u:p@192.168.1.2/path', 'channel': 3}).status_code == 200
    detect.assert_called_once()
    assert client.post('/api/auto-detect', json={'rtsp_url': 'rtsp://u:p@192.168.1.2/path', 'channel': 3}).status_code == 429
    assert detect.call_count == 1


@pytest.mark.parametrize('reply,expected', [(401, 'credentials'), (403, 'permissions'), (200, None)])
def test_detection_against_real_rtsp_authentication_socket(monkeypatch, reply, expected):
    import socket
    import threading

    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(2)
    listener.settimeout(5)
    port = listener.getsockname()[1]
    received, failures = [], []

    def respond():
        try:
            with listener:
                for index in range(2):
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(3)
                        request = bytearray()
                        while b'\r\n\r\n' not in request:
                            chunk = connection.recv(8192)
                            if not chunk:
                                break
                            request.extend(chunk)
                        received.append(request.decode('ascii'))
                        status = 401 if index == 0 else reply
                        challenge = 'WWW-Authenticate: Basic realm="Dahua test fixture"\r\n' if index == 0 else ''
                        connection.sendall(f'RTSP/1.0 {status} Test\r\nCSeq: {index + 1}\r\n{challenge}Content-Length: 0\r\n\r\n'.encode())
        except Exception as error:
            failures.append(error)

    thread = threading.Thread(target=respond, daemon=True)
    thread.start()
    decoder = Mock(return_value={'thumbnail': 'jpeg'})
    monkeypatch.setattr(discovery, '_try_rtsp', decoder)
    result = discovery.auto_diagnose_stream(f'rtsp://viewer:literal%23@127.0.0.1:{port}/custom')
    thread.join(6)
    assert not thread.is_alive()
    assert not failures
    assert len(received) == 2
    assert 'Authorization:' not in received[0]
    import base64
    assert 'Authorization: Basic ' + base64.b64encode(b'viewer:literal#').decode() in received[1]
    assert result['brand_hint'] == 'dahua'
    assert result['failed_stage'] == expected
    assert result['success'] is (reply == 200)
    assert 'literal' not in str(result)
    assert decoder.call_count == (1 if reply == 200 else 0)
