import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
from agent.local import onvif
from agent.local.server import create_app
from agent.local.store import SiteStore


@pytest.mark.parametrize('endpoint', ['http://8.8.8.8/service', 'http://192.168.1.3/service', 'http://user:pass@192.168.1.2/service', 'file:///etc/passwd', 'https://192.168.1.2/service'])
def test_onvif_does_not_forward_credentials_to_advertised_other_host(endpoint):
    with pytest.raises(ValueError):
        onvif._same_device(endpoint, '192.168.1.2', 'http')


def test_onvif_rejects_xml_entities():
    with pytest.raises(ValueError):
        onvif._xml(b'<!DOCTYPE test [<!ENTITY data SYSTEM "file:///secret">]><test/>')


def test_actual_profiles_are_used_not_guessed(monkeypatch):
    reader = onvif.OnvifReader('rtsp://viewer:literal%23@192.168.1.2/unknown')
    monkeypatch.setattr(reader, 'connect', Mock(return_value='http://192.168.1.2/onvif/device_service'))
    capabilities = ElementTree.fromstring(f'<root xmlns:tt="{onvif.SCHEMA}"><tt:Media><tt:XAddr>http://192.168.1.2/onvif/media</tt:XAddr></tt:Media></root>')
    profiles = ElementTree.fromstring(f'<root xmlns:trt="{onvif.MEDIA}" xmlns:tt="{onvif.SCHEMA}"><trt:Profiles token="actual-token"><tt:Name>Meeting room substream</tt:Name><tt:VideoSourceConfiguration><tt:SourceToken>actual-source</tt:SourceToken></tt:VideoSourceConfiguration></trt:Profiles></root>')
    monkeypatch.setattr(reader, '_request', Mock(side_effect=[capabilities, profiles]))
    try:
        result = reader.profiles()
        assert result['profiles'][0]['token'] == 'actual-token'
        assert result['profiles'][0]['source'] == 'actual-source'
        assert 'literal' not in str(result)
    finally:
        reader.close()


def test_device_stream_uri_encodes_actual_password_once(monkeypatch):
    reader = onvif.OnvifReader('rtsp://viewer:literal%23%2523@192.168.1.2/unknown')
    monkeypatch.setattr(reader, 'connect', Mock(return_value='http://192.168.1.2/onvif/device_service'))
    document = ElementTree.fromstring(f'<root xmlns:tt="{onvif.SCHEMA}"><tt:Uri>rtsp://192.168.1.2:8554/actual/path?source=2</tt:Uri></root>')
    monkeypatch.setattr(reader, '_request', Mock(return_value=document))
    try:
        assert reader.stream('http://192.168.1.2/onvif/media', 'actual-token') == 'rtsp://viewer:literal%23%2523@192.168.1.2:8554/actual/path?source=2'
    finally:
        reader.close()


def test_onvif_endpoint_requires_login_and_does_not_apply_failed_stream(tmp_path, monkeypatch):
    store = SiteStore(tmp_path)
    store.create_owner('owner', 'test-only-owner-password')
    licence = SimpleNamespace(status=lambda: SimpleNamespace(can_process=True))
    client = TestClient(create_app(store, licence, None), base_url='http://127.0.0.1')
    assert client.post('/api/onvif/profiles', json={}).status_code == 401
    client.post('/api/login', json={'username': 'owner', 'password': 'test-only-owner-password'})
    reader = Mock()
    reader.profiles.return_value = {'profiles': [{'token': 'actual'}], 'media_endpoint': 'http://192.168.1.2/onvif/media'}
    reader.stream.return_value = 'rtsp://u:p@192.168.1.2:8554/actual'
    factory = Mock(return_value=reader)
    monkeypatch.setattr(onvif, 'OnvifReader', factory)
    body = {'rtsp_url': 'rtsp://u:p@192.168.1.2/unknown', 'onvif_port': 80}
    assert client.post('/api/onvif/profiles', json={**body, 'rtsp_url': 'rtsp://u:p@8.8.8.8/unknown'}).status_code == 400
    factory.assert_not_called()
    assert client.post('/api/onvif/profiles', json=body).status_code == 200
    from agent import discovery
    monkeypatch.setattr(discovery, '_try_rtsp', Mock(return_value=None))
    test = client.post('/api/onvif/test-profile', json={**body, 'media_endpoint': 'http://192.168.1.2/onvif/media', 'profile_token': 'actual'})
    assert test.status_code == 200
    assert test.json()['success'] is False
    assert test.json()['path'] is None
    assert store.cameras() == []
    reader.close.assert_called()


@pytest.mark.parametrize('status', [400, 500])
def test_soap_authentication_fault_is_actionable_even_with_error_http_status(status):
    reader = onvif.OnvifReader('rtsp://viewer:literal%23@192.168.1.2/unknown')
    fault = f'<s:Envelope xmlns:s="{onvif.SOAP}"><s:Body><s:Fault><s:Code><s:Value>s:Sender</s:Value><s:Subcode><s:Value>ter:NotAuthorized</s:Value></s:Subcode></s:Code></s:Fault></s:Body></s:Envelope>'
    response = Mock(status_code=status)
    response.iter_content.return_value = [fault.encode()]
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    reader.session.post = Mock(return_value=response)
    try:
        with pytest.raises(ValueError, match='ONVIF-specific user') as failure:
            reader._request('http://192.168.1.2/onvif/device_service', 'GetCapabilities', onvif.DEVICE)
        assert 'literal' not in str(failure.value)
        assert reader.session.post.call_count == 1
    finally:
        reader.close()
