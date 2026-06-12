#!/usr/bin/env python3
"""
Vantag Edge Agent
=================

Runs on the retailer's local PC/tablet/Raspberry Pi.
Connects to LAN IP cameras and relays events + snapshots to Vantag cloud.

Usage:
    python vantag_agent.py

On first run, prompts for Vantag Cloud URL and Tenant ID, saves them to
~/.vantag/config.json, then starts scanning the local network for cameras.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("[!] Missing 'requests' library. Install with: pip install requests")
    sys.exit(1)

CONFIG_DIR = Path.home() / ".vantag"
CONFIG_FILE = CONFIG_DIR / "config.json"


# ─── Helpers ────────────────────────────────────────────────────────────────
def load_or_create_config() -> dict:
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text())

    print("=" * 60)
    print("  Vantag Edge Agent — First Run Setup")
    print("=" * 60)
    cloud = input("Vantag Cloud URL (e.g. https://retail-vantag.com): ").strip()
    tenant = input("Tenant ID: ").strip()
    cfg = {"cloud_url": cloud.rstrip("/"), "tenant_id": tenant}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    print(f"[✓] Config saved to {CONFIG_FILE}")
    return cfg


def get_local_subnet() -> str:
    """Return the /24 subnet of this machine, e.g. '192.168.1'."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ".".join(ip.split(".")[:3])


def scan_network_for_cameras(subnet: str, timeout: float = 0.3) -> list[str]:
    """Scan the /24 subnet for devices with port 554 (RTSP) open."""
    found = []
    print(f"[*] Scanning {subnet}.0/24 for IP cameras (port 554)...")
    for i in range(1, 255):
        ip = f"{subnet}.{i}"
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect((ip, 554))
            found.append(ip)
            print(f"    [✓] Camera detected at {ip}")
        except (socket.timeout, ConnectionRefusedError, OSError):
            pass
        finally:
            s.close()
    return found


def register_cameras(cfg: dict, cameras: list[str]) -> None:
    """POST discovered cameras to the Vantag cloud."""
    url = f"{cfg['cloud_url']}/api/edge/register"
    payload = {"tenant_id": cfg["tenant_id"], "cameras": cameras}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.ok:
            print(f"[✓] Registered {len(cameras)} camera(s) with cloud")
        else:
            print(f"[!] Cloud returned {r.status_code}: {r.text[:200]}")
    except requests.RequestException as e:
        print(f"[!] Cloud unreachable: {e}")


def send_heartbeat(cfg: dict) -> None:
    url = f"{cfg['cloud_url']}/api/edge/heartbeat"
    payload = {"tenant_id": cfg["tenant_id"], "timestamp": time.time()}
    try:
        requests.post(url, json=payload, timeout=5)
    except requests.RequestException:
        pass


# ─── Main loop ──────────────────────────────────────────────────────────────
def main() -> None:
    cfg = load_or_create_config()
    subnet = get_local_subnet()
    cameras = scan_network_for_cameras(subnet)

    if not cameras:
        print("[!] No IP cameras found on the local network.")
        print("    Make sure cameras are powered on and share this LAN.")
    else:
        register_cameras(cfg, cameras)

    print("[*] Agent running. Sending heartbeat every 30s. Ctrl+C to stop.")
    try:
        while True:
            send_heartbeat(cfg)
            time.sleep(30)
    except KeyboardInterrupt:
        print("\n[*] Shutting down.")


if __name__ == "__main__":
    main()
