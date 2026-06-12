"""
Vantag Camera Discovery Script
Scans 192.168.1.0/24 for IP cameras, probes camera ports, tests RTSP paths.
"""
import subprocess
import socket
import sys
import json
import os
import struct
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

SUBNET = "192.168.1"
CAMERA_PORTS = [554, 80, 8080, 8000, 37777, 34567, 8888, 81]

# Common RTSP paths by camera brand
RTSP_PATHS = [
    "/",
    "/stream",
    "/stream1",
    "/stream2",
    "/live",
    "/live/ch00_0",
    "/live/ch01_0",
    "/live/main",
    "/ch01.264",
    "/ch01.h264",
    "/videoMain",
    "/video1",
    "/video.h264",
    "/h264Preview_01_main",
    "/cam/realmonitor?channel=1&subtype=0",   # Dahua
    "/cam/realmonitor?channel=1&subtype=1",   # Dahua sub
    "/Streaming/Channels/101",                 # Hikvision
    "/Streaming/Channels/102",                 # Hikvision sub
    "/ONVIF/MediaInput",                       # ONVIF
    "/onvif/media",
    "/MediaInput/h264",
    "/mpeg4/media.amp",                        # Axis old
    "/axis-media/media.amp",                   # Axis
    "/user=admin_password=_channel=1_stream=0.sdp",  # Foscam
    "/videostream.cgi",
    "/11",
    "/12",
    "/1",
    "/2",
]

CREDENTIALS = [
    ("", ""),          # anonymous
    ("admin", ""),     # admin blank
    ("admin", "admin"),
    ("admin", "12345"),
    ("admin", "123456"),
    ("admin", "password"),
    ("admin", "1234"),
    ("admin", "888888"),
    ("admin", "666666"),
    ("root", ""),
    ("root", "root"),
    ("root", "12345"),
    ("guest", ""),
    ("guest", "guest"),
]


def ping(ip):
    """Ping a single IP, return True if alive."""
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "500", ip],
            capture_output=True, timeout=2
        )
        return result.returncode == 0
    except Exception:
        return False


def check_port(ip, port, timeout=1.5):
    """Check if a TCP port is open."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        result = s.connect_ex((ip, port))
        s.close()
        return result == 0
    except Exception:
        return False


def test_rtsp(url, timeout=3):
    """Test if an RTSP URL is accessible using socket-level RTSP OPTIONS."""
    try:
        parsed = url.replace("rtsp://", "")
        # Extract host and path
        if "@" in parsed:
            creds, rest = parsed.split("@", 1)
        else:
            rest = parsed
        host_port_path = rest
        if "/" in host_port_path:
            host_port = host_port_path.split("/")[0]
            path = "/" + "/".join(host_port_path.split("/")[1:])
        else:
            host_port = host_port_path
            path = "/"
        
        if ":" in host_port:
            host, port_str = host_port.rsplit(":", 1)
            port = int(port_str)
        else:
            host = host_port
            port = 554
        
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        
        # Send RTSP OPTIONS request
        request = f"OPTIONS {url} RTSP/1.0\r\nCSeq: 1\r\nUser-Agent: VantagScanner\r\n\r\n"
        s.sendall(request.encode())
        
        response = b""
        while True:
            try:
                chunk = s.recv(1024)
                if not chunk:
                    break
                response += chunk
                if b"\r\n\r\n" in response:
                    break
            except socket.timeout:
                break
        s.close()
        
        resp_str = response.decode("utf-8", errors="ignore")
        # Any RTSP response (200, 401, 403) means the camera is reachable on this path
        if "RTSP/1.0" in resp_str or "RTSP/1.1" in resp_str:
            if "200 OK" in resp_str:
                return "open"
            elif "401" in resp_str or "403" in resp_str:
                return "auth_required"
            else:
                return "reachable"
        return None
    except Exception:
        return None


def get_mac(ip):
    """Get MAC address from ARP table."""
    try:
        result = subprocess.run(["arp", "-a", ip], capture_output=True, text=True, timeout=2)
        for line in result.stdout.split("\n"):
            if ip in line:
                parts = line.split()
                for p in parts:
                    if "-" in p and len(p) == 17:
                        return p
    except Exception:
        pass
    return "unknown"


def scan_host(ip):
    """Full scan of a single host."""
    if not ping(ip):
        return None
    
    mac = get_mac(ip)
    open_ports = []
    for port in CAMERA_PORTS:
        if check_port(ip, port):
            open_ports.append(port)
    
    is_camera = bool(set(open_ports) & {554, 37777, 34567})
    
    return {
        "ip": ip,
        "mac": mac,
        "open_ports": open_ports,
        "is_camera_candidate": is_camera
    }


def probe_rtsp(ip, creds_list=None, paths=None):
    """Try to find working RTSP URL for a camera IP."""
    if paths is None:
        paths = RTSP_PATHS
    if creds_list is None:
        creds_list = CREDENTIALS
    
    working_urls = []
    
    for user, pw in creds_list:
        for path in paths:
            if user:
                url = f"rtsp://{user}:{pw}@{ip}:554{path}"
            else:
                url = f"rtsp://{ip}:554{path}"
            
            result = test_rtsp(url)
            if result == "open":
                print(f"    [SUCCESS] {url}")
                working_urls.append({"url": url, "status": "open", "requires_auth": False})
                return working_urls  # Found one that works, return immediately
            elif result in ("auth_required", "reachable"):
                print(f"    [REACHABLE] {url} ({result})")
                working_urls.append({"url": url, "status": result, "requires_auth": result == "auth_required"})
    
    return working_urls


def main():
    print("=" * 60)
    print("  VANTAG Camera Discovery Scanner")
    print(f"  Scanning: {SUBNET}.1 - {SUBNET}.254")
    print(f"  Started: {datetime.now().strftime('%H:%M:%S')}")
    print("=" * 60)
    
    # Step 1: Ping sweep (parallel)
    print("\n[Step 1] Pinging all hosts...")
    live_hosts = []
    
    with ThreadPoolExecutor(max_workers=50) as ex:
        futures = {ex.submit(ping, f"{SUBNET}.{i}"): f"{SUBNET}.{i}" for i in range(1, 255)}
        for future in as_completed(futures):
            ip = futures[future]
            if future.result():
                print(f"  ALIVE: {ip}")
                live_hosts.append(ip)
    
    live_hosts.sort(key=lambda x: int(x.split(".")[-1]))
    print(f"\n  Found {len(live_hosts)} live hosts: {', '.join(live_hosts)}")
    
    if not live_hosts:
        print("\n[WARNING] No hosts found. Check your network adapter or try running as Admin.")
        sys.exit(1)
    
    # Step 2: Port probe
    print("\n[Step 2] Probing camera ports on live hosts...")
    camera_candidates = []
    host_details = []
    
    for ip in live_hosts:
        print(f"\n  Checking {ip}...")
        mac = get_mac(ip)
        open_ports = []
        for port in CAMERA_PORTS:
            if check_port(ip, port):
                open_ports.append(port)
                print(f"    Port {port}: OPEN")
        
        is_camera = bool(set(open_ports) & {554, 37777, 34567})
        detail = {"ip": ip, "mac": mac, "open_ports": open_ports, "is_camera_candidate": is_camera}
        host_details.append(detail)
        
        if is_camera:
            camera_candidates.append(ip)
            print(f"    >> CAMERA CANDIDATE: {ip}")
        elif open_ports:
            print(f"    >> Open ports: {open_ports} (not a camera)")
    
    print(f"\n  Camera candidates: {camera_candidates if camera_candidates else 'None found'}")
    
    # Step 3: RTSP probe on camera candidates
    rtsp_results = {}
    if camera_candidates:
        print("\n[Step 3] Probing RTSP streams on camera candidates...")
        for ip in camera_candidates:
            print(f"\n  Testing RTSP on {ip}...")
            urls = probe_rtsp(ip)
            rtsp_results[ip] = urls
            if not urls:
                print(f"    No RTSP paths responded on {ip}")
    
    # Step 4: Summary
    print("\n" + "=" * 60)
    print("  DISCOVERY SUMMARY")
    print("=" * 60)
    print(f"\nLive hosts ({len(live_hosts)}): {', '.join(live_hosts)}")
    print(f"\nCamera candidates ({len(camera_candidates)}): {', '.join(camera_candidates) if camera_candidates else 'None'}")
    
    if rtsp_results:
        print("\nRTSP Results:")
        for ip, urls in rtsp_results.items():
            print(f"  {ip}:")
            if urls:
                for u in urls:
                    print(f"    {u['status']:15s} {u['url']}")
            else:
                print("    No RTSP response (check credentials or stream path)")
    
    # Save results
    results = {
        "scan_time": datetime.now().isoformat(),
        "subnet": f"{SUBNET}.0/24",
        "live_hosts": live_hosts,
        "host_details": host_details,
        "camera_candidates": camera_candidates,
        "rtsp_results": rtsp_results
    }
    out_file = r"D:\AI Algo\Collaterals\Profiles\Retail Nazar\camera_scan_results.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to: {out_file}")
    
    # Generate cameras.yaml snippet
    if camera_candidates:
        print("\n" + "=" * 60)
        print("  SUGGESTED cameras.yaml ENTRIES")
        print("=" * 60)
        for i, ip in enumerate(camera_candidates, 1):
            urls = rtsp_results.get(ip, [])
            best_url = "rtsp://admin:@{ip}:554/stream1"  # fallback
            if urls:
                open_ones = [u for u in urls if u["status"] == "open"]
                best_url = open_ones[0]["url"] if open_ones else urls[0]["url"]
            print(f"""
  - id: "cam-{i:02d}"
    name: "Camera {i}"
    rtsp_url: "{best_url}"
    location: "Location {i}"
    resolution:
      width: 1920
      height: 1080
    fps_target: 15
    enabled: true
    zones: []""")


if __name__ == "__main__":
    main()
