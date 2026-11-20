import hashlib
import re
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from agent.discovery import _describe_stream


def test_digest_authentication_reuses_challenge_connection():
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(2)
    listener.settimeout(3)
    port = listener.getsockname()[1]
    failures = []
    target = f'rtsp://127.0.0.1:{port}/stream1'

    def read_request(connection):
        received = bytearray()
        while b'\r\n\r\n' not in received:
            part = connection.recv(8192)
            if not part:
                break
            received.extend(part)
        return received.decode()

    def serve():
        try:
            with listener, listener.accept()[0] as connection:
                connection.settimeout(2)
                assert 'Authorization:' not in read_request(connection)
                connection.sendall(b'RTSP/1.0 401 Unauthorized\r\nCSeq: 1\r\nWWW-Authenticate: Digest realm="fixture", nonce="connection-bound"\r\nContent-Length: 0\r\n\r\n')
                request = read_request(connection)
                assert 'Authorization: Digest ' in request
                digest = lambda value: hashlib.md5(value.encode()).hexdigest()
                expected = digest(f'{digest("viewer:fixture:literal#")}:connection-bound:{digest("DESCRIBE:" + target)}')
                assert f'response="{expected}"' in request
                assert f'uri="{target}"' in request
                connection.sendall(b'RTSP/1.0 200 OK\r\nCSeq: 2\r\nContent-Length: 0\r\n\r\n')
        except Exception as error:
            failures.append(str(error))

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        result = _describe_stream(f'rtsp://viewer:literal%23@127.0.0.1:{port}/stream1', 1)
    finally:
        thread.join(4)
    assert not failures
    assert result['code'] == 200
    assert result['authenticated'] is True
