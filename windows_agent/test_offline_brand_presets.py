import hashlib
import socket
import sys
import threading
from pathlib import Path
from urllib.parse import quote

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from agent.local.store import stream_identity, stream_key


@pytest.mark.parametrize('path,channel,stream_type', [
    ('/axis-media/media.amp?camera=4&videocodec=h264', 4, 'Device default'),
    ('/profile2/media.smp', 1, 'Profile 2'),
    ('/LiveChannel/3/media.smp', 4, 'Device default'),
    ('/?line=4&inst=2', 4, 'Substream'),
    ('/Src/MediaInput/stream_2', 1, 'Substream'),
    ('/Src/MediaInput/stream_2/ch_4', 4, 'Substream'),
    ('/live2.sdp', 1, 'Substream'),
    ('/media2/stream.sdp?profile=Profile200', 1, 'Profile Profile200'),
    ('/defaultSecondary?streamType=u', 1, 'Substream'),
])
def test_brand_identity_preserves_safe_path_parameters(path, channel, stream_type):
    identity = stream_identity('rtsp://viewer:private@192.168.1.2:554' + path)
    assert identity['path'] == path
    assert identity['channel'] == channel
    assert identity['stream_type'] == stream_type
    assert 'private' not in str(identity)


@pytest.mark.parametrize('first,second', [
    ('/profile1/media.smp', '/profile2/media.smp'),
    ('/?line=4&inst=1', '/?inst=2&line=4'),
    ('/Src/MediaInput/stream_1/ch_4', '/Src/MediaInput/stream_2/ch_4'),
    ('/live.sdp', '/live2.sdp'),
    ('/defaultPrimary?streamType=u', '/defaultSecondary?streamType=u'),
])
def test_same_brand_camera_cannot_be_added_twice_by_switching_stream(first, second):
    prefix = 'rtsp://viewer:private@192.168.1.2'
    assert stream_key(prefix + first) == stream_key(prefix + second)


def test_stream_profile_and_custom_query_do_not_leak_credentials():
    identity = stream_identity('rtsp://u:secret@192.168.1.2/media2/stream.sdp?profile=Profile200&password=hidden')
    assert identity['path'] == '/media2/stream.sdp?profile=Profile200'
    assert identity['path_complete'] is False
    assert 'secret' not in str(identity)
    assert 'hidden' not in str(identity)


@pytest.mark.parametrize('status,expected', [(200, 'accepted'), (401, 'rejected'), (404, '404')])
def test_authenticated_diagnostic_uses_exact_path_and_encoded_password(status, expected):
    from agent.discovery import diagnose_rtsp

    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(2)
    listener.settimeout(5)
    port = listener.getsockname()[1]
    target = f'rtsp://127.0.0.1:{port}/cam/realmonitor?channel=3&subtype=1'
    received = []
    failures = []

    def serve():
        try:
            with listener:
                for index in range(2):
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(3)
                        request = bytearray()
                        while b'\r\n\r\n' not in request:
                            request.extend(connection.recv(8192))
                        received.append(request.decode('ascii'))
                        code = 401 if index == 0 else status
                        challenge = 'WWW-Authenticate: Digest realm="test", nonce="challenge", qop="auth", algorithm=MD5\r\n' if index == 0 else ''
                        connection.sendall(f'RTSP/1.0 {code} Test\r\nCSeq: {index + 1}\r\n{challenge}Content-Length: 0\r\n\r\n'.encode())
        except Exception as error:
            failures.append(error)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    result = diagnose_rtsp(f'rtsp://viewer:{quote("literal#%23", safe="")}@127.0.0.1:{port}/cam/realmonitor?channel=3&subtype=1', authenticate=True)
    thread.join(6)
    assert not failures
    assert not thread.is_alive()
    assert expected in result.lower()
    assert len(received) == 2
    assert 'Authorization:' not in received[0]
    assert target in received[1]
    assert 'literal' not in received[1]
    from urllib.request import parse_http_list, parse_keqv_list
    header = next(line for line in received[1].splitlines() if line.startswith('Authorization: Digest '))
    fields = parse_keqv_list(parse_http_list(header.removeprefix('Authorization: Digest ')))
    md5 = lambda value: hashlib.md5(value.encode()).hexdigest()
    expected_digest = md5(f'{md5("viewer:test:literal#%23")}:challenge:00000001:{fields["cnonce"]}:auth:{md5("DESCRIBE:" + target)}')
    assert fields['response'] == expected_digest
    assert fields['uri'] == target
    assert 'literal' not in result
