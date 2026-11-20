from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import subprocess
import time
from ctypes import wintypes
from pathlib import Path

import psutil
import requests

USER32 = ctypes.WinDLL("user32", use_last_error=True)
CALLBACK = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
USER32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
USER32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
USER32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
USER32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
USER32.SendMessageW.restype = ctypes.c_ssize_t


def windows(process_id: int) -> list[tuple[int, str]]:
    found = []

    def collect(handle, parameter):
        owner = wintypes.DWORD()
        USER32.GetWindowThreadProcessId(handle, ctypes.byref(owner))
        if owner.value == process_id:
            size = USER32.GetWindowTextLengthW(handle)
            value = ctypes.create_unicode_buffer(size + 1)
            USER32.GetWindowTextW(handle, value, size + 1)
            found.append((handle, value.value))
        return True

    USER32.EnumWindows(CALLBACK(collect), 0)
    return found


def click_button(parent: int, label: str) -> None:
    matches = []

    def collect(handle, parameter):
        value = ctypes.create_unicode_buffer(256)
        USER32.GetWindowTextW(handle, value, 256)
        if value.value == label:
            matches.append(handle)
        return True

    USER32.EnumChildWindows(wintypes.HWND(parent), CALLBACK(collect), 0)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {label!r} button, found {len(matches)}")
    USER32.SendMessageW(matches[0], 0x00F5, 0, 0)


def wait_for(check, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.3)
    raise TimeoutError("Normal-startup acceptance check timed out")


def app_process(executable: Path):
    for process in psutil.process_iter(["pid", "exe"]):
        if process.info["exe"] and Path(process.info["exe"]) == executable:
            return process
    return None


def listening_url(process):
    for connection in process.net_connections(kind="inet"):
        if connection.status == psutil.CONN_LISTEN and connection.laddr.ip == "127.0.0.1":
            return f"http://127.0.0.1:{connection.laddr.port}"
    return None


def verify(directory: Path, report: Path) -> dict:
    import os

    metadata = json.loads((directory / "TEST_PACKAGE.json").read_text(encoding="utf-8"))
    installed = Path(os.environ["LOCALAPPDATA"]) / "Vantag" / "OfflineEngineeringTest" / "Apps" / metadata["build_id"]
    executable = installed / "engine" / "VantagAgent.exe"
    installer = directory / metadata.get("installer_filename", "VantagOfflineTestSetup-1.11.5.exe")
    before = hashlib.file_digest(installer.open("rb"), "sha256").hexdigest()
    if installed.exists():
        raise RuntimeError("Use a fresh build for first-install acceptance; refusing to modify an established test installation")
    setup = subprocess.Popen([str(installer.resolve())], cwd=directory.resolve())
    app = None
    result = {"ok": False, "installer_sha256": before, "normal_launch": "No smoke-test or offline flags", "real_camera_accuracy_tested": False, "clean_pc_tested": False}
    try:
        handle = wait_for(lambda: next((handle for handle, title in windows(setup.pid) if title == "Vantag Offline Test Setup - 1.11.5"), None), 30)
        click_button(handle, "Install and open")
        app = wait_for(lambda: app_process(executable), 300)
        url = wait_for(lambda: listening_url(app), 180)
        client = requests.Session()
        client.trust_env = False

        def request(method, path, expected=200, **kwargs):
            response = client.request(method, url + path, timeout=60, **kwargs)
            if response.status_code != expected:
                raise RuntimeError(f"{path}: {response.status_code}: {response.text[:200]}")
            return response

        assert request("GET", "/api/bootstrap").json()["setup_required"] is True
        request("POST", "/api/setup", json={"username": "package-verification", "password": "isolated-acceptance-password-2026"})
        status = request("GET", "/api/status").json()
        assert status["mode"] == "offline"
        assert status["licence"]["state"] == "active"
        assert status["licence"]["claims"]["purpose"] == "engineering-test-not-for-resale"
        assert status["licence"]["claims"]["camera_limit"] == 8
        request("POST", "/api/site", json={"name": "Package verification only - no live cameras", "timezone": "Asia/Singapore"})
        camera_ids = []
        for channel in (1, 2):
            response = request("POST", "/api/cameras", json={"name": f"Disabled verification channel {channel}", "enabled": False, "rtsp_url": f"rtsp://test:test%23@192.168.254.254:554/Streaming/Channels/{channel}02", "detections": {"people_count": True}, "people_count_zones": [{"bbox": [0.1, 0.1, 0.8, 0.9]}]})
            camera_ids.append(response.json()["id"])
        cameras = request("GET", "/api/cameras").json()
        assert len(cameras) == 2 and len({item["id"] for item in cameras}) == 2
        request("POST", "/api/monitoring/start", json={})
        request("POST", "/api/monitoring/stop", json={})
        request("GET", "/api/backup")
        request("GET", "/api/counts.csv?day=2026-11-16")
        assert request("GET", "/api/events").json() == []
        request("GET", "/api/status", expected=403, headers={"Origin": "https://example.com"})
        request("POST", "/api/logout", json={})
        request("GET", "/api/status", expected=401)
        app.terminate()
        app.wait(20)
        subprocess.run([str(installed / "VantagOfflineTest.exe")], cwd=installed, check=True, timeout=30)
        app = wait_for(lambda: app_process(executable), 30)
        url = wait_for(lambda: listening_url(app), 180)
        client = requests.Session()
        client.trust_env = False
        assert request("GET", "/api/bootstrap").json()["setup_required"] is False
        request("POST", "/api/login", json={"username": "package-verification", "password": "isolated-acceptance-password-2026"})
        status = request("GET", "/api/status").json()
        assert status["licence"]["state"] == "active"
        assert status["site"]["timezone"] == "Asia/Singapore"
        assert {item["id"] for item in request("GET", "/api/cameras").json()} == set(camera_ids)
        assert status["runtime"]["error"] == ""
        result.update(ok=True, url=url, installed_directory=str(installed), app_pid=app.pid, licence=status["licence"], checks=["setup UI install button", "embedded payload extraction", "normal launcher startup", "local owner setup/login", "signed active test licence", "two disabled camera saves with zones", "backup and CSV", "origin/authentication protection", "restart with persistent owner/site/cameras/licence"], qualification="Development host, no actual NVR, no fabricated incidents or count samples")
        click_button(handle, "Close")
        setup.wait(20)
    except BaseException as error:
        result["error"] = repr(error)
        raise
    finally:
        report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    print(json.dumps(verify(arguments.directory.resolve(), arguments.report.resolve()), indent=2))
