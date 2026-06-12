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

Credentials are best-effort: anonymous first, then a small list of common
factory defaults. We NEVER silently persist a guessed password — when a host
answers on :554 but no path/credential yields a frame we flag
``needs_credentials=True`` so the dashboard can prompt the user.
"""
from __future__ import annotations

import base64
import logging
import re
import socket
import struct
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from ipaddress import IPv4Network
from typing import Optional

log = logging.getLogger("vantag.discovery")

try:
    import cv2  # type: ignore
except Exception:  # noqa: BLE001 - cv2 optional at import time
    cv2 = None  # type: ignore
else:
    # Silence OpenCV's own logger (the libav/FFmpeg 401 spam is muted via the
    # OPENCV_FFMPEG_LOGLEVEL env set in main.py before cv2 is imported).
    try:
        cv2.setLogLevel(0)  # 0 == SILENT
    except Exception:  # noqa: BLE001
        pass


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

# Common factory-default credential pairs. Tried ONLY after anonymous fails.
# We never persist these silently — a successful grab records which creds won so
# the user can confirm; a failure flags needs_credentials.
_DEFAULT_CREDS: list[tuple[Optional[str], Optional[str]]] = [
    (None, None),
    ("admin", "admin"),
    ("admin", ""),
    ("admin", "12345"),
    ("admin", "123456"),
    ("admin", "password"),
    ("root", "root"),
]

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
def _try_rtsp(ip: str, port: int, path: str,
              username: Optional[str], password: Optional[str]) -> Optional[dict]:
    """Open RTSP URL, read one frame within ~3s. Returns dict on success."""
    if cv2 is None:
        return None
    path = path if path.startswith("/") else f"/{path}"
    if username and password:
        from urllib.parse import quote
        u = quote(str(username), safe="")
        p = quote(str(password), safe="")
        rtsp_url = f"rtsp://{u}:{p}@{ip}:{port}{path}"
    else:
        rtsp_url = f"rtsp://{ip}:{port}{path}"

    cap = None
    try:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 3000)
        cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000)
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
    all_paths = _candidate_paths(brand_hint)
    for username, password in creds:
        # Anonymous: try the full path list (open cameras vary widely).
        # Credentialed guesses: only probe the most likely paths. If a
        # credential is correct it opens one of these quickly; if it 401s on
        # all of them the password is simply wrong, so skip the long tail
        # instead of hammering every path (this is what caused the endless
        # scan + wall of "401 Unauthorized" lines in the console).
        probe_paths = all_paths if (username, password) == (None, None) else all_paths[:6]
        for path in probe_paths:
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
