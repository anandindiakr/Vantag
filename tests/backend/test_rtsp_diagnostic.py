import hashlib
import re
import shutil
import socket
import subprocess
import threading
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Requires Windows PowerShell")
@pytest.mark.parametrize("inline", [False, True])
@pytest.mark.parametrize("algorithm,qop,final_code", [
    ("MD5", None, 200),
    ("MD5", "auth", 200),
    ("MD5-SESS", "auth", 200),
    ("MD5", None, 401),
    ("MD5", None, 404),
])
def test_powershell_authenticated_describe(tmp_path, algorithm, qop, final_code, inline):
    password = "fixture#@%1"
    nonce = "fixture-nonce"
    realm = "fixture-realm"
    requests = []
    errors = []
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(2)
    listener.settimeout(15)
    port = listener.getsockname()[1]

    def md5(value):
        return hashlib.md5(value.encode("utf-8")).hexdigest()

    def serve():
        try:
            with listener:
                for sequence in (1, 2):
                    connection, _ = listener.accept()
                    with connection:
                        connection.settimeout(5)
                        data = bytearray()
                        while b"\r\n\r\n" not in data:
                            chunk = connection.recv(4096)
                            assert chunk
                            data.extend(chunk)
                        request = data.decode("utf-8")
                        requests.append(request)
                        assert password not in request
                        if sequence == 1:
                            assert "Authorization:" not in request
                            challenge = f'Digest realm="{realm}", nonce="{nonce}", algorithm={algorithm}'
                            if qop:
                                challenge += f', qop="{qop}"'
                            response = f"RTSP/1.0 401 Unauthorized\r\nCSeq: 1\r\nWWW-Authenticate: {challenge}\r\nContent-Length: 0\r\n\r\n"
                        else:
                            authorization = re.search(r"(?im)^Authorization: Digest (.+)$", request).group(1)
                            fields = {match[0]: match[1] or match[2] for match in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]+))', authorization)}
                            ha1 = md5(f"admin:{realm}:{password}")
                            if algorithm == "MD5-SESS":
                                ha1 = md5(f"{ha1}:{nonce}:{fields['cnonce']}")
                            uri = f"rtsp://127.0.0.1:{port}/Streaming/Channels/101"
                            assert fields["uri"] == uri
                            ha2 = md5(f"DESCRIBE:{uri}")
                            if qop:
                                expected = md5(f"{ha1}:{nonce}:00000001:{fields['cnonce']}:auth:{ha2}")
                            else:
                                expected = md5(f"{ha1}:{nonce}:{ha2}")
                            assert fields["response"] == expected
                            body = "v=0\r\nm=video 0 RTP/AVP 96\r\n" if final_code == 200 else ""
                            response = f"RTSP/1.0 {final_code} Result\r\nCSeq: 2\r\nContent-Length: {len(body)}\r\n\r\n{body}"
                        encoded = response.encode("ascii")
                        connection.sendall(encoded[:23])
                        connection.sendall(encoded[23:])
        except Exception as error:
            errors.append(error)

    server = threading.Thread(target=serve, daemon=True)
    server.start()
    filename = "Test-VantagRtsp-Inline.ps1" if inline else "Test-VantagRtsp.ps1"
    script = Path(__file__).resolve().parents[2] / "scripts" / filename
    invocation = f". '{script}'; Test-VantagRtsp" if inline else f"& '{script}'"
    report = tmp_path / "result.txt"
    command = (
        f"$secure = ConvertTo-SecureString '{password}' -AsPlainText -Force; "
        "$credential = New-Object System.Management.Automation.PSCredential('admin', $secure); "
        f"{invocation} -NvrAddress 127.0.0.1 -Port {port} -Credential $credential -ReportPath '{report}'"
    )
    process = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True, text=True, timeout=25,
    )
    server.join(timeout=16)
    assert not errors, errors
    assert not server.is_alive()
    assert process.returncode == 0, process.stdout + process.stderr
    assert len(requests) == 2
    result = report.read_text(encoding="utf-8-sig")
    assert f"With supplied credentials: RTSP {final_code}" in result
    assert password not in result
    assert nonce not in result
    assert "Authorization:" not in result
    assert "response=" not in result
