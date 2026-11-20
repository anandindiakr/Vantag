"""
Camera auto-discovery for the Vantag Windows Edge Agent.

This runs ON the store LAN (the agent is the only component physically on the
tenant's private network), so it can find 192.168.x.x cameras that the cloud
backend can never reach.

Pipeline:
  1. _local_subnet()     -> derive the host's /24 from the primary interface.
  2. _tcp_probe()        -> concurrent socket sweep for RTSP/ONVIF/HTTP ports.
  3. _ws_discovery()     -> raw UDP WS-Discovery (ONVIF) for brand/model hints.
  4. _resolve_rtsp()     -> brute-force brand RTSP presets, grab one frame +
                            base64 JPEG thumbnail (ports backend _try_rtsp_path).
  5. run_discovery()     -> orchestrate; return a list of discovered cameras.

Credentials are best-effort: anonymous access or explicitly supplied credentials
only. We never guess factory passwords, because repeated failed guesses can lock
an NVR account. A reachable host without a decoded frame is not confirmed video.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import logging
import os
import re
import socket
import struct
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from ipaddress import IPv4Network
from typing import Optional
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from urllib.request import parse_http_list, parse_keqv_list

log = logging.getLogger("vantag.discovery")

os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

try:
    import cv2  # type: ignore
except Exception:  # noqa: BLE001 - cv2 optional at import time
    cv2 = None  # type: ignore


# ---------------------------------------------------------------------------
# Brand RTSP presets (ported from backend cameras_router._BRAND_RTSP_PRESETS)
# ---------------------------------------------------------------------------
_BRAND_RTSP_PRESETS: dict = {
    "hikvision": {"port": 554, "paths": ["/Streaming/Channels/101", "/Streaming/Channels/102", "/h264/ch1/main/av_stream"]},
    "dahua":     {"port": 554, "paths": ["/cam/realmonitor?channel=1&subtype=0", "/cam/realmonitor?channel=1&subtype=1"]},
    "cpplus":    {"port": 554, "paths": ["/cam/realmonitor?channel=1&subtype=0"]},
    "tplink":    {"port": 554, "paths": ["/stream1", "/stream2"]},
    "reolink":   {"port": 554, "paths": ["/h264Preview_01_main", "/h264Preview_01_sub"]},
    "uniview":   {"port": 554, "paths": ["/media/video1", "/media/video2"]},
    "axis":      {"port": 554, "paths": ["/axis-media/media.amp"]},
    "bosch":     {"port": 554, "paths": ["/rtsp_tunnel"]},
    "ezviz":     {"port": 554, "paths": ["/Streaming/Channels/101"]},
    "xiaomi":    {"port": 554, "paths": ["/live/ch00_0"]},
    "onvif":     {"port": 554, "paths": ["/onvif/media_service", "/onvif1", "/onvif2"]},
    "generic":   {"port": 554, "paths": ["/stream", "/stream1", "/live", "/live.sdp", "/"]},
}

# Map a path back to the brand that owns it (for labelling discovered cams).
_PATH_TO_BRAND: dict = {}
for _brand, _preset in _BRAND_RTSP_PRESETS.items():
    for _p in _preset["paths"]:
        _PATH_TO_BRAND.setdefault(_p, _brand)

_DEFAULT_CREDS: list[tuple[Optional[str], Optional[str]]] = [(None, None)]

_PROBE_PORTS = [554, 8000, 80]
_TCP_TIMEOUT = 0.6           # per-host port connect timeout (seconds)
_TCP_WORKERS = 128           # concurrent socket probes
_RTSP_WORKERS = 8            # concurrent cv2 RTSP probes (heavier)


# ---------------------------------------------------------------------------
# 1) Subnet detection
# ---------------------------------------------------------------------------
def _is_private(ip: str) -> bool:
    """Return True if *ip* is an RFC-1918 private or link-local address."""
    return (
        ip.startswith("192.168.")
        or ip.startswith("10.")
        or ip.startswith("172.16.") or ip.startswith("172.17.")
        or ip.startswith("172.18.") or ip.startswith("172.19.")
        or ip.startswith("172.2")  # 172.20–172.29
        or ip.startswith("172.30.") or ip.startswith("172.31.")
    )


def _local_subnet() -> Optional[IPv4Network]:
    """Return the agent host's /24 network using the default outbound interface.

    Falls back to the first RFC-1918 address found on the host if the
    default route points at a VPN/cloud interface.
    """
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if _is_private(ip):
            return IPv4Network(f"{ip}/24", strict=False)
    except Exception as e:  # noqa: BLE001
        log.warning("primary subnet detect failed: %s", e)
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:  # noqa: BLE001
                pass
    # Primary outbound interface is non-private (VPN, cloud).
    # Walk all IPv4 addresses on this host and return the first private one.
    return _first_private_subnet()


def _first_private_subnet() -> Optional[IPv4Network]:
    """Return the /24 of the first RFC-1918 IPv4 address found on this host."""
    try:
        hostname = socket.gethostname()
        for addrinfo in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = addrinfo[4][0]
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            if _is_private(ip):
                return IPv4Network(f"{ip}/24", strict=False)
    except Exception as e:  # noqa: BLE001
        log.warning("fallback subnet detect failed: %s", e)
    return None


def _all_private_subnets() -> list[IPv4Network]:
    """Return /24s for every RFC-1918 interface on this host (de-duplicated).

    This catches machines with multiple adapters — e.g. both a 10.x.x.x VPN
    adapter *and* a 192.168.x.x store LAN adapter.
    """
    nets: list[IPv4Network] = []
    seen: set[str] = set()
    try:
        hostname = socket.gethostname()
        for addrinfo in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = addrinfo[4][0]
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            if not _is_private(ip):
                continue
            net = IPv4Network(f"{ip}/24", strict=False)
            key = str(net)
            if key not in seen:
                seen.add(key)
                nets.append(net)
    except Exception as e:  # noqa: BLE001
        log.warning("all-subnets detect failed: %s", e)
    return nets


# ---------------------------------------------------------------------------
# 2) TCP port sweep
# ---------------------------------------------------------------------------
def _check_host(ip: str, ports: list[int]) -> Optional[dict]:
    """Return {ip, open_ports:[...]} if any probe port is open, else None."""
    open_ports: list[int] = []
    for port in ports:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(_TCP_TIMEOUT)
            if sock.connect_ex((ip, port)) == 0:
                open_ports.append(port)
        except Exception:  # noqa: BLE001
            pass
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:  # noqa: BLE001
                    pass
    if open_ports:
        return {"ip": ip, "open_ports": open_ports}
    return None


def _tcp_probe(network: IPv4Network, ports: Optional[list[int]] = None) -> list[dict]:
    """Concurrently sweep every host in *network* for the probe ports."""
    ports = ports or _PROBE_PORTS
    hosts = [str(h) for h in network.hosts()]
    found: list[dict] = []
    with ThreadPoolExecutor(max_workers=_TCP_WORKERS) as pool:
        futures = {pool.submit(_check_host, ip, ports): ip for ip in hosts}
        for fut in as_completed(futures):
            try:
                res = fut.result()
            except Exception:  # noqa: BLE001
                res = None
            if res:
                found.append(res)
    log.info("tcp_probe: %d live host(s) on %s", len(found), network)
    return found


# ---------------------------------------------------------------------------
# 3) ONVIF WS-Discovery (raw UDP multicast — no heavy dependency)
# ---------------------------------------------------------------------------
_WS_DISCOVERY_MSG = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
    'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
    'xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
    '<e:Header>'
    '<w:MessageID>uuid:{msg_id}</w:MessageID>'
    '<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
    '<w:Action e:mustUnderstand="true">'
    'http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>'
    '</e:Header>'
    '<e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>'
    '</e:Envelope>'
)

_XADDR_RE = re.compile(r"https?://([0-9]{1,3}(?:\.[0-9]{1,3}){3})", re.IGNORECASE)
_SCOPE_BRAND_RE = re.compile(
    r"onvif://www\.onvif\.org/(?:name|hardware|manufacturer)/([^ <]+)", re.IGNORECASE
)


def _ws_discovery(timeout: float = 3.0) -> dict[str, dict]:
    """Best-effort ONVIF WS-Discovery. Returns {ip: {brand, model, onvif:True}}."""
    results: dict[str, dict] = {}
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(timeout)
        msg = _WS_DISCOVERY_MSG.format(msg_id=uuid.uuid4()).encode("utf-8")
        sock.sendto(msg, ("239.255.255.250", 3702))

        import time as _time
        deadline = _time.monotonic() + timeout
        while _time.monotonic() < deadline:
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            except Exception:  # noqa: BLE001
                break
            text = data.decode("utf-8", errors="ignore")
            ip_match = _XADDR_RE.search(text)
            if not ip_match:
                continue
            ip = ip_match.group(1)
            brand = None
            model = None
            scope = _SCOPE_BRAND_RE.search(text)
            if scope:
                token = scope.group(1).replace("%20", " ").strip()
                brand = token.split()[0] if token else None
                model = token
            entry = results.setdefault(ip, {"onvif": True})
            if brand and not entry.get("brand"):
                entry["brand"] = brand
            if model and not entry.get("model"):
                entry["model"] = model
    except Exception as e:  # noqa: BLE001
        log.warning("ws_discovery failed: %s", e)
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:  # noqa: BLE001
                pass
    if results:
        log.info("ws_discovery: %d ONVIF device(s)", len(results))
    return results


# ---------------------------------------------------------------------------
# 4) RTSP path resolution + thumbnail (ported from backend _try_rtsp_path)
# ---------------------------------------------------------------------------
def _rtsp_exchange(connection, request: str, timeout: float) -> bytes:
    import time
    deadline = time.monotonic() + timeout
    connection.settimeout(timeout)
    connection.sendall(request.encode("utf-8"))
    response = bytearray()
    expected = None
    while len(response) < 65536:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("RTSP response timed out")
        connection.settimeout(remaining)
        chunk = connection.recv(min(4096, 65536 - len(response)))
        if not chunk:
            break
        response.extend(chunk)
        if expected is None and b"\r\n\r\n" in response:
            header, _, body = response.partition(b"\r\n\r\n")
            match = re.search(rb"(?im)^content-length:\s*(\d+)", header)
            expected = len(header) + 4 + (int(match[1]) if match else 0)
            if expected > 65536:
                raise ValueError("RTSP response exceeds diagnostic limit")
        if expected is not None and len(response) >= expected:
            break
    return bytes(response)


def _authenticated_rtsp_status(parsed, target: str, challenges: list[str], timeout: float, *, structured: bool = False, connection=None) -> str | dict:
    username, password = unquote(parsed.username or ""), unquote(parsed.password or "")
    authorization = None
    for challenge in challenges:
        if not challenge.lower().startswith("digest "):
            continue
        fields = parse_keqv_list(parse_http_list(challenge[7:]))
        algorithm = fields.get("algorithm", "MD5").upper()
        if algorithm not in {"MD5", "MD5-SESS"}:
            continue
        realm, nonce = fields.get("realm", ""), fields.get("nonce", "")
        if not nonce or any(char in username + realm + nonce + fields.get("opaque", "") for char in "\r\n"):
            return "Invalid RTSP authentication challenge; credentials were not retried."
        qops = [value.strip().lower() for value in fields.get("qop", "").split(",") if value.strip()]
        if qops and "auth" not in qops:
            continue
        cnonce = secrets.token_hex(16)
        def digest(value: str) -> str:
            return hashlib.md5(value.encode("utf-8")).hexdigest()
        def quoted(value: str) -> str:
            return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
        first = digest(f"{username}:{realm}:{password}")
        if algorithm == "MD5-SESS":
            first = digest(f"{first}:{nonce}:{cnonce}")
        second = digest("DESCRIBE:" + target)
        response = digest(f"{first}:{nonce}:00000001:{cnonce}:auth:{second}" if qops else f"{first}:{nonce}:{second}")
        authorization = f'Digest username={quoted(username)}, realm={quoted(realm)}, nonce={quoted(nonce)}, uri={quoted(target)}, response="{response}", algorithm={algorithm}'
        if qops:
            authorization += f', qop=auth, nc=00000001, cnonce="{cnonce}"'
        elif algorithm == "MD5-SESS":
            authorization += f', cnonce="{cnonce}"'
        if "opaque" in fields:
            authorization += ", opaque=" + quoted(fields["opaque"])
        break
    if authorization is None:
        if not any(challenge.lower().startswith("basic ") for challenge in challenges):
            return "RTSP authentication method is unsupported; credentials were not retried."
        authorization = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    request = f"DESCRIBE {target} RTSP/1.0\r\nCSeq: 2\r\nAccept: application/sdp\r\nAuthorization: {authorization}\r\n\r\n"
    response_bytes = b""
    if connection is not None:
        try:
            response_bytes = _rtsp_exchange(connection, request, timeout)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            response_bytes = b""
    if connection is None or not response_bytes:
        with socket.create_connection((parsed.hostname, parsed.port or 554), timeout=timeout) as retry_connection:
            response_bytes = _rtsp_exchange(retry_connection, request, timeout)
    match = re.match(rb"RTSP/\d\.\d\s+(\d{3})", response_bytes)
    code = int(match[1]) if match else None
    if structured:
        return {"code": code, "authenticated": True}
    if code == 200:
        return "RTSP credentials were accepted for this exact path (authenticated DESCRIBE 200), but video decoding failed. Check H.264 encoding, stream encryption, session limits and TCP transport."
    if code == 401:
        return "Device rejected an authenticated RTSP request (401) using the supplied credentials. Re-enter the actual device password, including #; check RTSP/remote live-view permissions and account lockout. Web login access alone does not confirm RTSP access. No other paths or passwords were tried."
    if code == 403:
        return "Device rejected RTSP access (authenticated 403). Check account permissions and stream security."
    if code == 404:
        return "Device returned authenticated RTSP 404 for this exact channel/path. Confirm the recorder brand and enabled channel; access restrictions may also hide streams."
    return f"Authenticated RTSP diagnostic returned {code or 'no valid response'}. No video was verified."


def diagnose_rtsp(url: str, timeout: float = 3.0, *, authenticate: bool = False) -> str:
    try:
        if authenticate:
            initial = urlsplit(url)
            if initial.scheme != "rtsp" or not initial.hostname:
                return "Invalid RTSP address. Check the saved stream URL."
            description = _describe_stream(url, timeout)
            if description.get("auth_error"):
                return description["auth_error"]
            code = description.get("code")
            if code == 200:
                return "RTSP credentials were accepted for this exact path (authenticated DESCRIBE 200), but video decoding failed. Check H.264 encoding, stream encryption, session limits and TCP transport."
            if code == 401:
                return "Device rejected an authenticated RTSP request (401), including same-connection authentication. This does not establish that the password is wrong: RTSP permissions, firmware compatibility or a concealed invalid path can produce this result. Use ONVIF device-reported profiles, and verify the ONVIF-specific media account with the device administrator. No other passwords were tried."
            if code == 403:
                return "Device rejected RTSP access (authenticated 403). Check account permissions and stream security."
            if code == 404:
                return "Device returned authenticated RTSP 404 for this exact channel/path. Confirm the enabled channel using ONVIF profiles; access restrictions may also hide streams."
            return f"RTSP diagnostic returned {code or 'no valid response'}. No video was verified."
        parsed = urlsplit(url)
        host = parsed.hostname
        if parsed.scheme.lower() != "rtsp" or not host:
            return "Invalid RTSP address. Check the saved stream URL."
        port = parsed.port or 554
        authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        target = urlunsplit(("rtsp", authority, parsed.path or "/", parsed.query, ""))
        if "\r" in target or "\n" in target:
            return "Invalid RTSP address. Check the saved stream URL."
        request = f"DESCRIBE {target} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n"
        with socket.create_connection((host, port), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(request.encode("ascii"))
            response = bytearray()
            while b"\r\n\r\n" not in response and len(response) < 16384:
                chunk = connection.recv(min(4096, 16384 - len(response)))
                if not chunk:
                    break
                response.extend(chunk)
        headers = bytes(response).split(b"\r\n\r\n", 1)[0].decode("ascii", errors="replace")
        lines = headers.splitlines()
        status = re.match(r"RTSP/\d\.\d\s+(\d{3})", lines[0] if lines else "")
        if not status:
            return "Port reachable, but no valid RTSP response. Check the NVR RTSP service and port."
        code = int(status.group(1))
        if code == 401:
            challenges = [line.partition(":")[2].strip() for line in lines[1:]
                          if line.lower().startswith("www-authenticate:")]
            algorithms = []
            compatible = False
            for challenge in challenges:
                if challenge.lower().startswith("basic "):
                    compatible = True
                if challenge.lower().startswith("digest "):
                    match = re.search(r'algorithm\s*=\s*"?([A-Za-z0-9_-]+)', challenge, re.IGNORECASE)
                    algorithm = match.group(1).upper() if match else "MD5"
                    algorithms.append(algorithm)
                    compatible = compatible or algorithm in {"MD5", "MD5-SESS"}
            if algorithms and not compatible:
                offered = ", ".join(sorted(set(algorithms)))
                return (
                    f"NVR offers RTSP Digest {offered}, incompatible with this bundled FFmpeg authentication. "
                    "Ask the NVR administrator for a supported secure streaming configuration or compatible gateway."
                )
            if authenticate and parsed.username:
                return _authenticated_rtsp_status(parsed, target, challenges, timeout)
            return (
                "RTSP authentication is required (401 from a password-free diagnostic). "
                "This does not prove the password is wrong. Check RTSP permissions, account lockout and stream security."
            )
        if code == 404:
            return "NVR returned RTSP 404: verify this NVR channel and main/sub-stream path; access restrictions may also hide channels."
        if code == 403:
            return "NVR returned RTSP 403: check remote live-view permission, account restrictions and stream security."
        if code == 200:
            return "NVR returned an RTSP description (200), but video decoding failed. Check codec, stream encryption, TCP transport and session limits."
        return f"NVR returned RTSP {code}. Check NVR stream configuration and connection limits."
    except (socket.timeout, TimeoutError):
        return "NVR did not answer RTSP within the diagnostic timeout. Check routing, firewall and RTSP service."
    except (OSError, ValueError, UnicodeError):
        return "RTSP diagnostic could not connect. Check the saved host/port, network route and NVR RTSP service."


def _describe_stream(url: str, timeout: float) -> dict:
    parsed = urlsplit(url)
    host, port = parsed.hostname, parsed.port or 554
    authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
    target = urlunsplit(("rtsp", authority, parsed.path or "/", parsed.query, ""))
    if any(character in target for character in "\r\n"):
        raise ValueError("Invalid RTSP path")
    request = f"DESCRIBE {target} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n"
    with socket.create_connection((host, port), timeout=timeout) as connection:
        response = _rtsp_exchange(connection, request, timeout)
        lines = response.split(b"\r\n\r\n", 1)[0].decode("ascii", errors="replace").splitlines()
        match = re.match(r"RTSP/\d\.\d\s+(\d{3})", lines[0] if lines else "")
        result = {"code": int(match[1]) if match else None, "authenticated": False, "brand_hint": None}
        hints = " ".join(line for line in lines[1:] if line.lower().startswith(("server:", "www-authenticate:"))).lower()
        for brand in ("hikvision", "dahua", "axis", "hanwha", "bosch", "vivotek", "avigilon", "uniview", "reolink"):
            if brand in hints:
                result["brand_hint"] = brand
                break
        if 'realm="htms"' in hints:
            result["brand_hint"] = "HTMS firmware family (OEM brand unknown)"
        if result["code"] == 401 and parsed.username:
            challenges = [line.partition(":")[2].strip() for line in lines[1:] if line.lower().startswith("www-authenticate:")]
            authenticated = _authenticated_rtsp_status(parsed, target, challenges, timeout, structured=True, connection=connection)
            if isinstance(authenticated, dict):
                result.update(authenticated)
            else:
                result["auth_error"] = authenticated
        return result


def auto_diagnose_stream(url: str, *, channel: int = 1, timeout: float = 1.5) -> dict:
    parsed = urlsplit(url)
    if parsed.scheme != "rtsp" or not parsed.hostname or parsed.fragment or not parsed.path.startswith("/") or not 1 <= channel <= 256:
        raise ValueError("Use a valid RTSP address and channel from 1 to 256")
    stages = {name: "not tested" for name in ("network", "protocol", "credentials", "path", "decode")}
    result = {"success": False, "path": None, "thumbnail": None, "brand_hint": None, "stages": stages, "attempts": []}

    def failed(stage: str, message: str) -> dict:
        stages[stage] = "failed"
        return {**result, "failed_stage": stage, "message": message}

    current = parsed.path + ("?" + parsed.query if parsed.query else "")
    from .local.store import stream_identity
    current_channel = stream_identity(url)["channel"]
    candidates = [current] if current_channel is None or current_channel == channel else []
    candidates.extend([
        f"/cam/realmonitor?channel={channel}&subtype=1",
        f"/Streaming/Channels/{channel}02",
        f"/cam/realmonitor?channel={channel}&subtype=0",
        f"/Streaming/Channels/{channel}01",
        f"/LiveChannel/{channel - 1}/media.smp",
        f"/axis-media/media.amp?camera={channel}&videocodec=h264",
        f"/?line={channel}&inst=2",
        f"/Src/MediaInput/stream_2/ch_{channel}",
    ])
    if channel == 1:
        candidates.extend(["/stream1", "/live2.sdp", "/profile2/media.smp", "/media/video1", "/live.sdp"])
    candidates = list(dict.fromkeys(candidates))[:10]
    import time
    deadline = time.monotonic() + 24
    for path in candidates:
        if time.monotonic() >= deadline:
            break
        candidate = urlunsplit(("rtsp", parsed.netloc, path.split("?", 1)[0], path.partition("?")[2], ""))
        try:
            description = _describe_stream(candidate, min(timeout, max(0.1, (deadline - time.monotonic()) / 2)))
        except (OSError, ValueError, UnicodeError):
            return failed("network", "Cannot complete an RTSP connection to this IP and port. Check the LAN connection, RTSP port/service and firewall. No camera configuration was changed.")
        stages["network"] = "reachable"
        code = description["code"]
        result["attempts"].append({"candidate": len(result["attempts"]) + 1, "status": code, "authenticated_request": description.get("authenticated", False)})
        result["brand_hint"] = result["brand_hint"] or description.get("brand_hint")
        if code is None:
            return failed("protocol", "Port answered without a valid RTSP response. Verify the RTSP service port, not the web-login port.")
        stages["protocol"] = "RTSP response received"
        if description.get("auth_error"):
            return failed("credentials", description["auth_error"])
        if code == 401:
            return failed("credentials", "The device returned authenticated RTSP 401 after a same-connection challenge response. This alone cannot distinguish account/RTSP permission rejection, firmware compatibility or an invalid path hidden by the device. Use Read device profiles (ONVIF) to request actual stream choices without knowing the brand. Web and ONVIF accounts may differ. No alternate paths or passwords were tried.")
        if code == 403:
            return failed("permissions", "Device forbids this RTSP stream (403). Ask the device administrator to enable this account's remote live-view/RTSP channel permission and check stream security. Detection stopped.")
        stages["credentials"] = "accepted for stream" if code == 200 and description.get("authenticated") else "not required for description" if code == 200 else "unconfirmed"
        if code == 200:
            stages["path"] = "RTSP description found"
            decoded = _try_rtsp(parsed.hostname, parsed.port or 554, path, unquote(parsed.username or ""), unquote(parsed.password or ""))
            if not decoded:
                return failed("decode", "RTSP description found, but no video frame decoded. Check H.264 codec, stream encryption, TCP transport and recorder connection limits. No path was applied; this is not verified live video.")
            stages["decode"] = "frame decoded"
            return {**result, "success": True, "path": path, "thumbnail": decoded.get("thumbnail"), "failed_stage": None, "message": "Decoded video verified. Detected path filled into the form, not saved. Check that the picture is the intended camera/channel, then Save camera. Brand hint is not manufacturer identification; AI accuracy was not tested."}
        if code not in {400, 404}:
            return failed("path", f"Device returned RTSP {code}. Check recorder stream/session settings with its administrator. No configuration was changed.")
    return failed("path", "No video path found in the bounded template search for the selected channel. A 404 does not prove credentials are accepted. Verify the channel is enabled and obtain its exact RTSP path from the device's ONVIF GetStreamUri or installer. This is not an exhaustive brand/model search.")


def _try_rtsp(ip: str, port: int, path: str,
              username: Optional[str], password: Optional[str]) -> Optional[dict]:
    """Open RTSP URL, read one frame within ~3s. Returns dict on success."""
    if cv2 is None:
        return None
    path = path if path.startswith("/") else f"/{path}"
    if username:
        safe_user = quote(username, safe="")
        safe_password = quote(password or "", safe="")
        rtsp_url = f"rtsp://{safe_user}:{safe_password}@{ip}:{port}{path}"
    else:
        rtsp_url = f"rtsp://{ip}:{port}{path}"

    cap = None
    try:
        cap = cv2.VideoCapture(
            rtsp_url, cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000],
        )
        if not cap.isOpened():
            return None
        ok, frame = cap.read()
        if not ok or frame is None:
            return None
        ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        thumbnail = base64.b64encode(buf.tobytes()).decode("utf-8") if ok2 else None
        return {"path": path, "thumbnail": thumbnail, "rtsp_url": rtsp_url,
                "username": username, "password": password}
    except Exception:  # noqa: BLE001
        return None
    finally:
        if cap is not None:
            try:
                cap.release()
            except Exception:  # noqa: BLE001
                pass


def _candidate_paths(brand_hint: Optional[str]) -> list[str]:
    """Ordered, de-duped candidate paths — brand-hinted first, then the rest."""
    ordered: list[str] = []
    seen: set = set()

    def _add(paths: list[str]) -> None:
        for p in paths:
            if p not in seen:
                ordered.append(p)
                seen.add(p)

    if brand_hint:
        key = brand_hint.strip().lower()
        for bk, preset in _BRAND_RTSP_PRESETS.items():
            if bk in key or key in bk:
                _add(preset["paths"])
    for preset in _BRAND_RTSP_PRESETS.values():
        _add(preset["paths"])
    return ordered


def _resolve_rtsp(ip: str, brand_hint: Optional[str],
                  creds: Optional[list[tuple]] = None) -> dict:
    """Try candidate paths x credentials for *ip*. Returns a discovery record."""
    creds = creds or _DEFAULT_CREDS
    paths = _candidate_paths(brand_hint)
    for path in paths:
        for username, password in creds:
            res = _try_rtsp(ip, 554, path, username, password)
            if res:
                brand = brand_hint or _PATH_TO_BRAND.get(path)
                used_default = bool(username) and (username, password) != (None, None)
                return {
                    "ip": ip,
                    "port": 554,
                    "brand": brand,
                    "rtsp_path": res["path"],
                    "rtsp_url": res["rtsp_url"],
                    "thumbnail_b64": res.get("thumbnail"),
                    "needs_credentials": False,
                    # surface that a default-cred guess was used so the UI can
                    # ask the user to confirm/replace it (never trusted silently)
                    "used_default_credential": used_default,
                }
    # Host is alive on :554 but nothing yielded a frame -> needs credentials.
    return {
        "ip": ip,
        "port": 554,
        "brand": brand_hint,
        "rtsp_path": None,
        "rtsp_url": None,
        "thumbnail_b64": None,
        "needs_credentials": True,
        "used_default_credential": False,
    }


# ---------------------------------------------------------------------------
# 5) Orchestrator
# ---------------------------------------------------------------------------
def run_discovery(creds: Optional[list[tuple]] = None,
                  scan_subnet: Optional[str] = None) -> list[dict]:
    """Discover cameras on the local LAN.

    Args:
        creds:       Optional credential list (username, password) pairs.
        scan_subnet: Optional CIDR string to pin the scan to a specific subnet
                     (e.g. "192.168.254.0/24").  When set the auto-detection is
                     skipped entirely — useful when the agent machine has a VPN
                     adapter that grabs the default route.

    Returns a list of records:
      {ip, port, brand, model, rtsp_path, rtsp_url, thumbnail_b64,
       onvif, needs_credentials, used_default_credential, confidence}
    """
    # ── Determine networks to scan ─────────────────────────────────────────
    if scan_subnet:
        try:
            networks = [IPv4Network(scan_subnet, strict=False)]
            log.info("Using configured scan_subnet: %s", scan_subnet)
        except ValueError as exc:
            log.warning("Invalid scan_subnet '%s': %s — falling back to auto-detect", scan_subnet, exc)
            networks = _all_private_subnets() or [_local_subnet()]
    else:
        networks = _all_private_subnets()
        if not networks:
            # Last resort: try the default route
            net = _local_subnet()
            networks = [net] if net else []

    networks = [n for n in networks if n is not None]
    if not networks:
        log.error("discovery aborted: could not determine any local subnet")
        return []

    log.info("camera discovery started on %d subnet(s): %s",
             len(networks), ", ".join(str(n) for n in networks))

    # ── ONVIF WS-Discovery (fast UDP — covers all subnets at once) ─────────
    onvif_hints = _ws_discovery(timeout=3.0)

    # ── TCP sweep across every detected subnet ─────────────────────────────
    live: list[dict] = []
    for net in networks:
        live.extend(_tcp_probe(net))

    # Union of TCP-live hosts and ONVIF responders.
    candidate_ips: dict[str, dict] = {}
    for h in live:
        candidate_ips[h["ip"]] = {"open_ports": h.get("open_ports", [])}
    for ip, hint in onvif_hints.items():
        candidate_ips.setdefault(ip, {"open_ports": [80]})

    # Only attempt RTSP on hosts that expose :554 OR were seen via ONVIF.
    rtsp_targets = [
        ip for ip, meta in candidate_ips.items()
        if 554 in meta.get("open_ports", []) or ip in onvif_hints
    ]
    log.info("resolving RTSP on %d candidate host(s)", len(rtsp_targets))

    discovered: list[dict] = []
    with ThreadPoolExecutor(max_workers=_RTSP_WORKERS) as pool:
        futures = {}
        for ip in rtsp_targets:
            brand_hint = onvif_hints.get(ip, {}).get("brand")
            futures[pool.submit(_resolve_rtsp, ip, brand_hint, creds)] = ip
        for fut in as_completed(futures):
            ip = futures[fut]
            try:
                rec = fut.result()
            except Exception as e:  # noqa: BLE001
                log.warning("resolve_rtsp failed for %s: %s", ip, e)
                continue
            hint = onvif_hints.get(ip, {})
            rec["model"] = hint.get("model")
            rec["onvif"] = bool(hint.get("onvif"))
            if not rec.get("brand") and hint.get("brand"):
                rec["brand"] = hint["brand"]
            # confidence: frame grabbed > onvif-only > tcp-only
            if rec.get("rtsp_url"):
                rec["confidence"] = 0.9
            elif rec["onvif"]:
                rec["confidence"] = 0.5
            else:
                rec["confidence"] = 0.3
            discovered.append(rec)

    discovered.sort(key=lambda r: r.get("confidence", 0), reverse=True)
    log.info("camera discovery finished: %d camera(s)", len(discovered))
    return discovered


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cams = run_discovery()
    print(f"\nDiscovered {len(cams)} camera(s):\n")
    for c in cams:
        thumb = "yes" if c.get("thumbnail_b64") else "no"
        print(
            f"  {c['ip']:<15} brand={c.get('brand') or '?':<10} "
            f"path={c.get('rtsp_path') or '-':<28} "
            f"onvif={c.get('onvif')} thumb={thumb} "
            f"needs_creds={c.get('needs_credentials')} "
            f"conf={c.get('confidence')}"
        )
