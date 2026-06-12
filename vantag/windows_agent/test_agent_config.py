"""
Regression test for the Edge Agent download config contract.

The backend (/api/agent/download) writes a config.json that the agent parses via
AgentConfig.load(), which does:

    cams = [CameraConfig(**c) for c in raw.pop("cameras", [])]
    return cls(**raw, cameras=cams)

If the server emits a camera key that is NOT a CameraConfig field (it used to emit
`camera_id` and `fps_target`), CameraConfig(**c) raises TypeError, load() swallows it,
and the agent silently falls back to an EMPTY config (no api_key) -> a downloaded
agent that never connects. These tests lock the schema so that never regresses.

Run:  python test_agent_config.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.config import AgentConfig, CameraConfig  # noqa: E402

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


def _server_config(camera_block):
    """A top-level config exactly as backend/api/edge_router.py emits it."""
    return {
        "api_key": "sk_live_abc123",
        "agent_id": "agent-xyz",
        "backend_url": "https://retail-vantag.com",
        "mqtt_host": "retail-vantag.com",
        "mqtt_port": 1883,
        "tenant_id": "tenant-1",
        "cameras": camera_block,
    }


def _load_like_agent(raw: dict) -> AgentConfig:
    """Replicate AgentConfig.load()'s parsing core (no filesystem/APPDATA)."""
    raw = dict(raw)
    cams = [CameraConfig(**c) for c in raw.pop("cameras", [])]
    return AgentConfig(**raw, cameras=cams)


print("\n--- Edge Agent download config contract ---")


def test_current_server_shape_parses():
    cfg = _server_config([
        {
            "id": "cam-1",
            "name": "Entrance",
            "rtsp_url": "rtsp://10.0.0.5:554/stream1",
            "location": "Front door",
        }
    ])
    agent = _load_like_agent(cfg)
    check("current server config parses into a configured agent",
          agent.is_configured() and agent.api_key == "sk_live_abc123")
    check("camera parsed with correct id/name/rtsp",
          len(agent.cameras) == 1
          and agent.cameras[0].id == "cam-1"
          and agent.cameras[0].name == "Entrance"
          and agent.cameras[0].rtsp_url.startswith("rtsp://"),
          f"cameras={agent.cameras}")


def test_empty_rtsp_is_tolerated():
    cfg = _server_config([
        {"id": "cam-2", "name": "Aisle", "rtsp_url": "", "location": ""}
    ])
    agent = _load_like_agent(cfg)
    check("camera with blank rtsp_url still loads (manual fill later)",
          agent.is_configured() and len(agent.cameras) == 1,
          f"cameras={agent.cameras}")


def test_no_cameras_still_configured():
    agent = _load_like_agent(_server_config([]))
    check("zero-camera tenant downloads a configured agent",
          agent.is_configured() and agent.cameras == [])


def test_old_broken_shape_would_fail():
    """Proves the bug we fixed: the OLD camera keys raise TypeError."""
    bad = _server_config([
        {
            "camera_id": "cam-1",        # wrong key (should be 'id')
            "name": "Entrance",
            "rtsp_url": "rtsp://x",
            "fps_target": 10,            # not a CameraConfig field
        }
    ])
    raised = False
    try:
        _load_like_agent(bad)
    except TypeError:
        raised = True
    check("old camera schema (camera_id/fps_target) raises TypeError",
          raised,
          "expected TypeError from CameraConfig(**c) with stale keys")


def test_top_level_keys_are_all_valid_fields():
    valid = set(AgentConfig.__dataclass_fields__.keys())
    server_keys = set(_server_config([]).keys())
    extra = server_keys - valid
    check("every top-level server config key is a real AgentConfig field",
          not extra, f"unknown keys={extra}")


test_current_server_shape_parses()
test_empty_rtsp_is_tolerated()
test_no_cameras_still_configured()
test_old_broken_shape_would_fail()
test_top_level_keys_are_all_valid_fields()

print(f"\n=== {PASS} passed, {FAIL} failed ===")
sys.exit(1 if FAIL else 0)
