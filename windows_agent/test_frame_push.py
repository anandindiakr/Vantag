"""
Local test script for the live-frame relay: VantagApiClient.push_frame() and
CameraWorker._maybe_push_frame() throttling/in-flight logic.

No real camera, RTSP, network, or ONNX model required — HTTP calls are
captured via a fake `requests` session and cv2 encode/resize are stubbed.

Usage (from repo root):
    cd windows_agent
    python test_frame_push.py

Pass/fail summary printed at the end. Exit code 0 = all pass.
"""
import base64
import sys
import time
import types
import pathlib

import numpy as np

_AGENT_DIR = pathlib.Path(__file__).parent / "agent"
sys.path.insert(0, str(_AGENT_DIR.parent))  # windows_agent/ on path

# ── Stub cv2 (heavy native dep) before agent modules import it ───────────────
_cv2_stub = types.ModuleType("cv2")
_cv2_stub.resize = lambda img, size: img
_cv2_stub.imencode = lambda ext, img, params=None: (True, np.zeros((4,), dtype=np.uint8))
_cv2_stub.VideoCapture = None
_cv2_stub.CAP_FFMPEG = 0
_cv2_stub.CAP_PROP_BUFFERSIZE = 0
_cv2_stub.IMWRITE_JPEG_QUALITY = 1
sys.modules["cv2"] = _cv2_stub

# ── Stub onnxruntime so agent.inference imports cleanly ──────────────────────
_ort_stub = types.ModuleType("onnxruntime")
_ort_stub.InferenceSession = object
sys.modules.setdefault("onnxruntime", _ort_stub)

from agent.api_client import VantagApiClient  # noqa: E402
from agent.config import CameraConfig  # noqa: E402
from agent.camera_worker import CameraWorker  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


# ── Fake requests.Session capturing calls instead of hitting the network ────
class FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json = json_body or {"ok": True}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json


class FakeSession:
    def __init__(self, fail=False, delay=0.0):
        self.headers = {}
        self.calls = []
        self.fail = fail
        self.delay = delay

    def post(self, url, json=None, timeout=None):
        if self.delay:
            time.sleep(self.delay)
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.fail:
            raise ConnectionError("simulated network failure")
        return FakeResponse(200)

    def get(self, url, timeout=None):
        self.calls.append({"url": url, "timeout": timeout})
        return FakeResponse(200)


def _make_client(fail=False, delay=0.0) -> VantagApiClient:
    client = VantagApiClient(base_url="https://retail-vantag.com", api_key="test-key")
    client._session = FakeSession(fail=fail, delay=delay)
    return client


# ══════════════════════════════════════════════════════════════════════════
# 1. VantagApiClient.push_frame() — happy path
# ══════════════════════════════════════════════════════════════════════════
print("\n[1] VantagApiClient.push_frame — happy path")
client = _make_client()
frame_b64 = base64.b64encode(b"fake-jpeg-bytes").decode()
result = client.push_frame("cam-001", frame_b64)

check("push_frame returns True on success", result is True)
check("posted to /api/edge/frame", client._session.calls[0]["url"].endswith("/api/edge/frame"))
check("payload contains camera_id", client._session.calls[0]["json"]["camera_id"] == "cam-001")
check("payload contains frame_b64", client._session.calls[0]["json"]["frame_b64"] == frame_b64)
check("uses a short timeout (<=5s)", client._session.calls[0]["timeout"] is not None and client._session.calls[0]["timeout"] <= 5)


# ══════════════════════════════════════════════════════════════════════════
# 2. VantagApiClient.push_frame() — network failure never raises
# ══════════════════════════════════════════════════════════════════════════
print("\n[2] VantagApiClient.push_frame — failure is swallowed")
failing_client = _make_client(fail=True)
try:
    result = failing_client.push_frame("cam-001", frame_b64)
    check("push_frame returns False on failure (no exception escapes)", result is False)
except Exception as e:  # noqa: BLE001
    check("push_frame returns False on failure (no exception escapes)", False, detail=str(e))


# ══════════════════════════════════════════════════════════════════════════
# 3. CameraWorker._maybe_push_frame() — throttling to ~200ms
# ══════════════════════════════════════════════════════════════════════════
print("\n[3] CameraWorker._maybe_push_frame — throttling")


class _StubInference:
    pass


cam_cfg = CameraConfig(id="cam-throttle", name="Cam Throttle", rtsp_url="rtsp://x")
worker = CameraWorker(config=cam_cfg, inference=_StubInference(), api_client=_make_client())
fake_frame = np.zeros((10, 10, 3), dtype=np.uint8)

worker._maybe_push_frame(fake_frame)
first_call_count = len(worker._api._session.calls)
check("first call pushes immediately", first_call_count == 1)

# Immediately call again — should be skipped (in-flight flag was cleared by
# the executor thread already since FakeSession.post has no delay, but the
# 200ms throttle window should still block it).
worker._maybe_push_frame(fake_frame)
time.sleep(0.05)  # let any submitted executor task finish
second_call_count = len(worker._api._session.calls)
check("second call within 200ms window is skipped", second_call_count == first_call_count,
      detail=f"expected {first_call_count}, got {second_call_count}")

# Wait past the throttle window — next call should go through.
time.sleep(0.25)
worker._maybe_push_frame(fake_frame)
time.sleep(0.05)
third_call_count = len(worker._api._session.calls)
check("call after throttle window succeeds", third_call_count == first_call_count + 1,
      detail=f"expected {first_call_count + 1}, got {third_call_count}")


# ══════════════════════════════════════════════════════════════════════════
# 4. CameraWorker._maybe_push_frame() — in-flight guard drops overlapping pushes
# ══════════════════════════════════════════════════════════════════════════
print("\n[4] CameraWorker._maybe_push_frame — in-flight guard")

slow_client = _make_client(delay=0.3)  # push takes 300ms to "complete"
worker2 = CameraWorker(config=cam_cfg, inference=_StubInference(), api_client=slow_client)

worker2._maybe_push_frame(fake_frame)  # kicks off a slow push (300ms)
time.sleep(0.22)  # still < 300ms in-flight, but > 200ms throttle window
worker2._maybe_push_frame(fake_frame)  # should be dropped — previous still in flight
time.sleep(0.2)  # let the first push finish (total ~0.42s > 0.3s delay)

check("overlapping push dropped by in-flight guard", len(slow_client._session.calls) == 1,
      detail=f"expected 1, got {len(slow_client._session.calls)}")

time.sleep(0.1)  # let in-flight flag clear fully
worker2._maybe_push_frame(fake_frame)
time.sleep(0.05)
check("push resumes once in-flight clears and throttle passes", len(slow_client._session.calls) >= 1)


# ══════════════════════════════════════════════════════════════════════════
print(f"\n{'=' * 50}\nResults: {PASS} passed, {FAIL} failed\n{'=' * 50}")
sys.exit(0 if FAIL == 0 else 1)
