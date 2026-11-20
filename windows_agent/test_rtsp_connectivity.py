import ast
import asyncio
import logging
import sys
import socket
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import discovery


@pytest.mark.parametrize("password", ["demo#pass", "demo@pass", "demo%23pass", ""])
def test_discovery_encodes_literal_credentials_and_sets_open_timeouts(monkeypatch, password):
    capture = Mock()
    capture.isOpened.return_value = True
    capture.read.return_value = (True, object())
    encoded = Mock()
    encoded.tobytes.return_value = b"jpeg"
    video = Mock(CAP_FFMPEG=1900, CAP_PROP_OPEN_TIMEOUT_MSEC=53,
                 CAP_PROP_READ_TIMEOUT_MSEC=54, IMWRITE_JPEG_QUALITY=1)
    video.VideoCapture.return_value = capture
    video.imencode.return_value = (True, encoded)
    monkeypatch.setattr(discovery, "cv2", video)

    result = discovery._try_rtsp("192.168.1.102", 554, "/Streaming/Channels/201", "admin", password)

    assert result is not None
    from urllib.parse import unquote
    parsed = urlsplit(result["rtsp_url"])
    assert parsed.hostname == "192.168.1.102"
    assert parsed.fragment == ""
    assert unquote(parsed.password) == password
    args = video.VideoCapture.call_args.args
    assert args[2] == [53, 3000, 54, 3000]
    capture.release.assert_called_once()


def test_discovery_does_not_report_open_socket_as_video(monkeypatch):
    capture = Mock()
    capture.isOpened.return_value = True
    capture.read.return_value = (False, None)
    video = Mock()
    video.VideoCapture.return_value = capture
    monkeypatch.setattr(discovery, "cv2", video)

    assert discovery._try_rtsp("192.168.1.102", 554, "/Streaming/Channels/101", "admin", "test") is None
    capture.release.assert_called_once()


def load_probe_job(namespace):
    source_path = Path(__file__).parent / "agent" / "main.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_run_rtsp_probe_job")
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace["_run_rtsp_probe_job"]


def test_exact_connection_test_never_substitutes_another_nvr_channel():
    session = Mock()
    probe = Mock()
    probe._try_rtsp.return_value = {
        "path": "/Streaming/Channels/201", "rtsp_url": "rtsp://example/201", "thumbnail": "jpeg",
    }
    namespace = {"_api": SimpleNamespace(_session=session, base_url="https://example.test"),
                 "discovery": probe, "log": logging.getLogger("test")}
    run_job = load_probe_job(namespace)

    run_job({"job_id": "job", "ip": "192.168.1.102", "port": 554,
             "username": "admin", "password": "test#", "rtsp_path": "/Streaming/Channels/201"})

    probe._candidate_paths.assert_not_called()
    probe._try_rtsp.assert_called_once_with("192.168.1.102", 554, "/Streaming/Channels/201", "admin", "test#")
    payload = session.post.call_args.kwargs["json"]
    assert payload["success"] is True
    assert payload["thumbnail_base64"] == "jpeg"
    assert payload["tried_paths"] == ["/Streaming/Channels/201"]


def test_lan_test_queues_agent_frame_check(monkeypatch):
    from backend.api import cameras_router, edge_router

    queue = Mock(return_value="job-123")
    monkeypatch.setattr(edge_router, "queue_rtsp_probe", queue)
    body = cameras_router.TestConnectionRequest(ip="192.168.1.102", username="admin", password="test#",
                                                rtsp_path="/Streaming/Channels/201")
    result = asyncio.run(cameras_router.test_camera_connection(body, user={"tenant_id": "tenant-a"}))

    assert result.success is False
    assert result.queued is True
    assert result.job_id == "job-123"
    queue.assert_called_once_with("tenant-a", "192.168.1.102", 554, "admin", "test#",
                                  rtsp_path="/Streaming/Channels/201")


def test_probe_results_are_tenant_scoped():
    from backend.api import cameras_router, edge_router
    from fastapi import HTTPException

    job = edge_router.queue_rtsp_probe("tenant-a", "192.168.1.102")
    try:
        with pytest.raises(HTTPException) as raised:
            asyncio.run(cameras_router.auto_detect_path_result(job, user={"tenant_id": "tenant-b"}))
        assert raised.value.status_code == 404
    finally:
        edge_router._rtsp_probe_results.pop(job, None)
        edge_router._rtsp_probe_jobs.pop("tenant-a", None)


def test_discovery_never_guesses_factory_passwords():
    assert discovery._DEFAULT_CREDS == [(None, None)]


@pytest.mark.parametrize("statuses,expected", [({"cam-1": "offline", "cam-2": "online"}, 2), ({}, 0), (None, None)])
def test_heartbeat_refreshes_reported_camera_count(statuses, expected):
    from backend.api import edge_router

    session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())
    agent = SimpleNamespace(id="agent-a", tenant_id="tenant-a")
    asyncio.run(edge_router.heartbeat(edge_router.HeartbeatBody(camera_statuses=statuses), agent=agent, session=session))
    statement = session.execute.call_args_list[0].args[0]
    parameters = statement.compile().params
    assert parameters.get("camera_count") == expected


@pytest.mark.parametrize("status,headers,expected", [
    (401, 'WWW-Authenticate: Digest realm="NVR", nonce="secret", algorithm="SHA-256"\r\n', "SHA-256"),
    (401, 'WWW-Authenticate: Digest realm="NVR", nonce="secret", algorithm="MD5"\r\n', "authentication"),
    (401, 'WWW-Authenticate: Digest realm="NVR", algorithm="SHA-256"\r\nWWW-Authenticate: Basic realm="NVR"\r\n', "authentication"),
    (404, "", "channel"),
    (403, "", "permission"),
    (200, "", "description"),
])
def test_rtsp_diagnostics_against_real_local_socket(status, headers, expected):
    received = []
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(3)
    port = listener.getsockname()[1]

    def respond():
        with listener:
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(3)
                received.append(connection.recv(8192).decode("ascii"))
                response = f"RTSP/1.0 {status} Test\r\nCSeq: 1\r\n{headers}\r\n".encode("ascii")
                connection.sendall(response[:17])
                connection.sendall(response[17:])

    server = threading.Thread(target=respond, daemon=True)
    server.start()
    result = discovery.diagnose_rtsp(f"rtsp://admin:do-not-send@127.0.0.1:{port}/Streaming/Channels/201")
    server.join(timeout=4)

    assert not server.is_alive()
    assert expected.lower() in result.lower()
    assert "do-not-send" not in received[0]
    assert "Authorization:" not in received[0]
    assert "/Streaming/Channels/201" in received[0]
    assert "secret" not in result
    if "Basic" in headers:
        assert "incompatible" not in result.lower()


def test_probe_reports_preserve_preview_and_reject_legacy_path_scans():
    from backend.api import cameras_router, edge_router

    job = edge_router.queue_rtsp_probe("tenant-a", "192.168.1.102", rtsp_path="/Streaming/Channels/201")
    try:
        agent = SimpleNamespace(tenant_id="tenant-a")
        body = edge_router.RtspProbeResultBody(
            job_id=job, success=True, rtsp_path="/Streaming/Channels/201",
            rtsp_url="rtsp://admin:secret@192.168.1.102:554/Streaming/Channels/201",
            tried_paths=["/Streaming/Channels/201"], thumbnail_base64="jpeg",
        )
        asyncio.run(edge_router.rtsp_probe_result(body, agent=agent))
        result = asyncio.run(cameras_router.auto_detect_path_result(job, user={"tenant_id": "tenant-a"}))
        assert result["success"] is True
        assert result["thumbnail_base64"] == "jpeg"
        assert "secret" not in result["rtsp_url"]

        body.tried_paths = ["/Streaming/Channels/101", "/Streaming/Channels/201"]
        asyncio.run(edge_router.rtsp_probe_result(body, agent=agent))
        result = asyncio.run(cameras_router.auto_detect_path_result(job, user={"tenant_id": "tenant-a"}))
        assert result["success"] is False
        assert "Update" in result["error"]
        assert result["thumbnail_base64"] is None

        body.success = False
        body.rtsp_path = None
        body.tried_paths = ["/Streaming/Channels/201"]
        body.error = "NVR offers RTSP Digest SHA-256"
        asyncio.run(edge_router.rtsp_probe_result(body, agent=agent))
        result = asyncio.run(cameras_router.auto_detect_path_result(job, user={"tenant_id": "tenant-a"}))
        assert result["error"] == body.error
    finally:
        edge_router._rtsp_probe_results.pop(job, None)
        edge_router._rtsp_probe_jobs.pop("tenant-a", None)


@pytest.mark.skipif(discovery.cv2 is None, reason="OpenCV is not installed")
def test_native_opencv_open_timeout_with_unresponsive_rtsp_service():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(6)
    port = listener.getsockname()[1]
    stop = threading.Event()

    def accept_without_rtsp_response():
        with listener:
            connection, _ = listener.accept()
            with connection:
                stop.wait(timeout=6)

    server = threading.Thread(target=accept_without_rtsp_response, daemon=True)
    server.start()
    started = time.monotonic()
    try:
        assert discovery._try_rtsp("127.0.0.1", port, "/Streaming/Channels/101", None, None) is None
        assert time.monotonic() - started < 5.5
    finally:
        stop.set()
        server.join(timeout=7)
