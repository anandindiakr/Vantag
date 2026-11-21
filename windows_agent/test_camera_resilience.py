import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from agent import camera_worker


def worker_for_capture():
    worker = camera_worker.CameraWorker.__new__(camera_worker.CameraWorker)
    worker.config = SimpleNamespace(id='test', name='Test camera', rtsp_url='rtsp://user:secret%23@192.168.1.20/stream')
    worker._stop_event = threading.Event()
    worker._target_fps = 5
    worker.consecutive_failures = 0
    worker.is_connected = False
    worker.MAX_FAILURES = 10
    worker._infer_inflight = threading.Event()
    worker._infer_executor = Mock()
    worker._maybe_push_frame = Mock()
    return worker


@pytest.fixture(autouse=True)
def accepted_stream_description(monkeypatch):
    monkeypatch.setattr(camera_worker, '_describe_stream', lambda *args: {'code': 200, 'authenticated': True}, raising=False)


@pytest.mark.parametrize('code', [401, 403])
def test_rejected_stream_credentials_pause_without_repeated_camera_logins(monkeypatch, code):
    worker = worker_for_capture()
    describe = Mock(return_value={'code': code, 'authenticated': True})
    capture = Mock()
    capture.isOpened.return_value = False
    monkeypatch.setattr(camera_worker, 'diagnose_rtsp', lambda *args: 'No decoded video')
    monkeypatch.setattr(camera_worker, '_describe_stream', describe)
    open_capture = Mock(return_value=capture)
    monkeypatch.setattr(camera_worker.cv2, 'VideoCapture', open_capture)
    waits = []
    def wait(timeout=None):
        waits.append(timeout)
        worker._stop_event.set()
    worker._stop_event.wait = wait
    worker._run()
    assert describe.call_count == 1
    open_capture.assert_called_once()
    capture.release.assert_called_once()
    assert waits == [None]
    assert not worker.is_connected
    assert 'paused' in worker.error_msg.lower()
    assert str(code) in worker.error_msg
    assert 'secret' not in worker.error_msg


def test_network_failure_keeps_bounded_automatic_reconnection(monkeypatch):
    worker = worker_for_capture()
    worker.consecutive_failures = 10000
    capture = Mock()
    capture.isOpened.return_value = False
    monkeypatch.setattr(camera_worker.cv2, 'VideoCapture', lambda *args: capture)
    monkeypatch.setattr(camera_worker, 'diagnose_rtsp', lambda *args: 'No decoded video')
    monkeypatch.setattr(camera_worker, '_describe_stream', Mock(side_effect=TimeoutError('private stream')))
    waits = []
    def wait(timeout=None):
        waits.append(timeout)
        worker._stop_event.set()
    worker._stop_event.wait = wait
    worker._run()
    assert waits == [60]
    assert 'private stream' not in worker.error_msg


def test_open_without_decoded_frames_does_not_reset_failure_backoff(monkeypatch):
    worker = worker_for_capture()
    worker.consecutive_failures = 4
    capture = Mock()
    capture.isOpened.return_value = True
    capture.grab.return_value = False
    monkeypatch.setattr(camera_worker.cv2, 'VideoCapture', lambda *args: capture)
    waits = []
    def wait(timeout=None):
        waits.append(timeout)
        worker._stop_event.set()
    worker._stop_event.wait = wait
    worker._run()
    assert waits == [32]
    assert worker.consecutive_failures == 5
    assert not worker.is_connected


def test_failed_capture_releases_nvr_session_before_retry_delay(monkeypatch):
    worker = worker_for_capture()
    capture = Mock()
    capture.isOpened.return_value = False
    monkeypatch.setattr(camera_worker.cv2, 'VideoCapture', lambda *args: capture)
    monkeypatch.setattr(camera_worker, 'diagnose_rtsp', lambda *args: 'No decoded video')
    released_at_wait = []
    def wait(timeout):
        released_at_wait.append(capture.release.called)
        worker._stop_event.set()
    worker._stop_event.wait = wait
    worker._run()
    assert released_at_wait == [True]
    assert capture.release.call_count == 1


def test_hot_add_inference_budget_takes_effect_without_reconnect(monkeypatch):
    worker = worker_for_capture()
    capture = Mock()
    capture.isOpened.return_value = True
    capture.grab.return_value = True
    capture.retrieve.return_value = (True, np.zeros((8, 8, 3), dtype=np.uint8))
    monkeypatch.setattr(camera_worker.cv2, 'VideoCapture', lambda *args: capture)
    clock = iter([100, 100, 100.5, 101, 101.5, 102, 102.5, 103])
    monkeypatch.setattr(camera_worker.time, 'time', lambda: next(clock))
    submitted = []
    def submit(*args):
        submitted.append(True)
        worker._target_fps = 0.25
        worker._infer_inflight.clear()
    worker._infer_executor.submit = submit
    pushed = []
    def push(frame):
        pushed.append(True)
        if len(pushed) == 3:
            worker._stop_event.set()
    worker._maybe_push_frame = push
    describe = Mock(side_effect=AssertionError('A working stream must not need a separate authentication probe'))
    monkeypatch.setattr(camera_worker, '_describe_stream', describe)
    worker._run()
    describe.assert_not_called()
    assert len(pushed) == 3
    assert len(submitted) == 1


def test_stop_drains_inference_before_site_storage_can_close():
    worker = worker_for_capture()
    worker._thread = Mock()
    worker._closed = False
    worker._rules = Mock()
    worker.stop()
    worker._infer_executor.shutdown.assert_called_once_with(wait=True, cancel_futures=True)


def test_runtime_exposes_each_worker_evidence_storage_failure(running_site):
    store, runtime, first = running_site
    worker = runtime.workers[0]
    worker.is_connected = False
    worker.current_fps = 0
    worker.inference_ms = 0
    worker.inference_error = ''
    worker._local_sink.error = 'Evidence could not be saved: OSError. Check local storage.'
    runtime.detector = SimpleNamespace(status={})
    status = runtime.status()
    assert status['cameras'][0]['evidence_error'] == worker._local_sink.error
    assert status['error']


def test_evidence_database_failure_is_visible_not_an_inference_crash():
    import sqlite3
    from agent.local.runtime import LocalSink
    store = Mock()
    store.record_event.side_effect = sqlite3.OperationalError('private database path must not escape')
    sink = LocalSink(store)
    assert sink.post_event({'event_type': 'fall_detected'}) is False
    assert 'OperationalError' in sink.error
    assert 'private database path' not in sink.error


from test_offline_live_configuration import running_site
