"""
backend/services/ai_config_service.py
======================================
AI-powered camera auto-discovery and configuration.
Probes a camera IP, detects brand, finds working RTSP URL,
and returns natural-language diagnostics if it fails.
"""
from __future__ import annotations

import asyncio
import base64
import socket
import subprocess
from typing import Any

import cv2

CAMERA_PORTS = [554, 80, 8080, 8000, 37777, 34567, 81, 8888]

# RTSP paths grouped by detected brand signature
RTSP_PATHS_BY_BRAND: dict[str, list[str]] = {
    "dahua": [
        "/cam/realmonitor?channel=1&subtype=0",
        "/cam/realmonitor?channel=1&subtype=1",
        "/live",
        "/stream1",
    ],
    "hikvision": [
        "/Streaming/Channels/101",
        "/Streaming/Channels/102",
        "/stream1",
        "/live",
    ],
    "xmeye": [
        "/user=admin_password=_channel=1_stream=0.sdp",
        "/11",
        "/12",
        "/stream1",
        "/live/ch00_0",
    ],
    "axis": [
        "/axis-media/media.amp",
        "/video1",
        "/mpeg4/media.amp",
        "/stream1",
    ],
    "generic": [
        "/",
        "/stream",
        "/stream1",
        "/stream2",
        "/live",
        "/live/ch00_0",
        "/live/main",
        "/ch01.264",
        "/videoMain",
        "/h264Preview_01_main",
        "/cam/realmonitor?channel=1&subtype=0",
        "/Streaming/Channels/101",
        "/user=admin_password=_channel=1_stream=0.sdp",
        "/11",
        "/video1",
    ],
}

CREDENTIALS = [
    ("", ""),
    ("admin", ""),
    ("admin", "admin"),
    ("admin", "12345"),
    ("admin", "123456"),
    ("admin", "password"),
    ("admin", "1234"),
    ("admin", "888888"),
    ("root", ""),
    ("root", "root"),
    ("guest", "guest"),
]

DIAGNOSTICS: dict[str, str] = {
    "unreachable": (
        "Cannot reach this IP address. Please check: "
        "(1) Camera is powered on and connected to the same network, "
        "(2) You entered the correct IP address, "
        "(3) Your phone/PC is on the same WiFi as your cameras."
    ),
    "no_rtsp_port": (
        "Camera found on the network but RTSP streaming port (554) is not open. "
        "Open your camera's web interface at http://{ip} and enable RTSP streaming "
        "in the Network or Video settings."
    ),
    "auth_required": (
        "Camera is reachable but requires a username/password. "
        "Try your camera's login credentials. Common defaults: "
        "admin/admin, admin/12345, admin/(blank). "
        "You can reset the camera using the reset button on the device."
    ),
    "path_not_found": (
        "Camera is accessible but the stream path was not found. "
        "Check your camera's manual for the correct RTSP stream URL, "
        "or contact the camera manufacturer's support."
    ),
    "timeout": (
        "Connection to camera timed out. The camera may be overloaded or "
        "on a slow network. Try again in a few seconds."
    ),
}


def _ping(ip: str) -> bool:
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "1000", ip],
            capture_output=True, timeout=3
        )
        return result.returncode == 0
    except Exception:
        return False


def _check_port(ip: str, port: int, timeout: float = 1.5) -> bool:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        result = s.connect_ex((ip, port))
        s.close()
        return result == 0
    except Exception:
        return False


def _detect_brand(ip: str, open_ports: list[int]) -> str:
    """Guess camera brand from open ports."""
    if 37777 in open_ports:
        return "dahua"
    if 34567 in open_ports:
        return "xmeye"
    if 8000 in open_ports and 554 in open_ports:
        return "hikvision"
    return "generic"


def _test_rtsp_options(url: str, timeout: float = 3.0) -> str | None:
    """Send RTSP OPTIONS to check if server responds. Returns status: open/auth/reachable/None."""
    try:
        parsed = url.replace("rtsp://", "")
        if "@" in parsed:
            _, rest = parsed.split("@", 1)
        else:
            rest = parsed
        if "/" in rest:
            host_port = rest.split("/")[0]
        else:
            host_port = rest
        host, port = (host_port.rsplit(":", 1) if ":" in host_port else (host_port, "554"))
        port = int(port)

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        req = f"OPTIONS {url} RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: VantagProbe\r\n\r\n"
        s.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = s.recv(1024)
            if not chunk:
                break
            resp += chunk
        s.close()
        resp_str = resp.decode("utf-8", errors="ignore")
        if "200 OK" in resp_str:
            return "open"
        if "401" in resp_str or "403" in resp_str:
            return "auth"
        if "RTSP" in resp_str:
            return "reachable"
        return None
    except Exception:
        return None


def _try_cv2_open(url: str, timeout_ms: int = 5000) -> tuple[bool, bytes | None]:
    """Try to open an RTSP stream with cv2 and grab one frame."""
    try:
        cap = cv2.VideoCapture(url)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms)
        if not cap.isOpened():
            cap.release()
            return False, None
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            return True, base64.b64encode(buf.tobytes()).decode()
        return True, None  # opened but no frame
    except Exception:
        return False, None


async def probe_camera(ip: str, credentials_hint: str | None = None) -> dict[str, Any]:
    """
    Full async probe of a camera IP.
    Returns: {success, rtsp_url, brand, resolution, thumbnail_b64, diagnostics, open_ports}
    """
    loop = asyncio.get_event_loop()

    # Step 1: Ping
    alive = await loop.run_in_executor(None, _ping, ip)
    if not alive:
        return {
            "success": False,
            "ip": ip,
            "diagnostics": DIAGNOSTICS["unreachable"],
            "step_failed": "ping",
        }

    # Step 2: Port scan
    open_ports = []
    for port in CAMERA_PORTS:
        is_open = await loop.run_in_executor(None, _check_port, ip, port, 1.5)
        if is_open:
            open_ports.append(port)

    if 554 not in open_ports:
        return {
            "success": False,
            "ip": ip,
            "open_ports": open_ports,
            "diagnostics": DIAGNOSTICS["no_rtsp_port"].format(ip=ip),
            "step_failed": "port_scan",
        }

    # Step 3: Brand detection
    brand = _detect_brand(ip, open_ports)

    # Step 4: Try RTSP paths
    paths = RTSP_PATHS_BY_BRAND.get(brand, []) + RTSP_PATHS_BY_BRAND["generic"]

    # Build credential list — try hints first
    creds = list(CREDENTIALS)
    if credentials_hint:
        # Insert hinted password at front
        creds = [("admin", credentials_hint), ("", credentials_hint)] + creds

    working_url = None
    auth_blocked = False
    thumbnail_b64 = None

    for user, pw in creds:
        for path in paths:
            if user:
                url = f"rtsp://{user}:{pw}@{ip}:554{path}"
            else:
                url = f"rtsp://{ip}:554{path}"

            status = await loop.run_in_executor(None, _test_rtsp_options, url, 3.0)
            if status == "auth":
                auth_blocked = True
                continue
            if status in ("open", "reachable"):
                # Try to get a frame
                success, thumb = await loop.run_in_executor(None, _try_cv2_open, url, 6000)
                if success:
                    working_url = url
                    thumbnail_b64 = thumb
                    break
        if working_url:
            break

    if not working_url:
        diag_key = "auth_required" if auth_blocked else "path_not_found"
        return {
            "success": False,
            "ip": ip,
            "brand": brand,
            "open_ports": open_ports,
            "diagnostics": DIAGNOSTICS[diag_key],
            "step_failed": "rtsp_probe",
        }

    return {
        "success": True,
        "ip": ip,
        "rtsp_url": working_url,
        "brand": brand,
        "open_ports": open_ports,
        "resolution": {"width": 1920, "height": 1080},
        "thumbnail_b64": thumbnail_b64,
        "diagnostics": None,
    }
