"""
Vantag Edge Agent — Direct Python Launcher

Use this to test the agent on a store LAN WITHOUT building the .exe first.
Requirements: Python 3.11 or 3.12 (3.14 may not be supported by pystray)

Usage:
    1. Place your config.json in this directory (copy from config.template.json)
    2. Edit config.json — set your api_key (get it from retail-vantag.com/download)
    3. Run:  python run_agent.py

The agent will:
  - Register with retail-vantag.com
  - Scan this LAN for cameras (192.168.x.x, port 554/8000/80)
  - Post discovered cameras to your dashboard
  - Start monitoring any configured cameras
  - Show a tray icon (Windows) for control

Logs are written to: %APPDATA%\\Vantag\\agent.log
"""
import sys
import os

# Ensure the windows_agent directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def check_requirements():
    missing = []
    for pkg in ["cv2", "numpy", "requests", "paho.mqtt", "pystray", "PIL", "psutil", "schedule"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"[ERROR] Missing packages: {missing}")
        print("Run:  pip install -r requirements.txt")
        sys.exit(1)

def check_config():
    import json
    from pathlib import Path
    cfg_path = Path(__file__).parent / "config.json"
    if not cfg_path.exists():
        print("[ERROR] config.json not found in this directory.")
        print("  1. Copy config.template.json to config.json")
        print("  2. Edit config.json and set your api_key")
        print("  3. Get your API key from: https://retail-vantag.com/download")
        sys.exit(1)
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not data.get("api_key"):
        print("[ERROR] api_key is empty in config.json.")
        print("  Get your API key from: https://retail-vantag.com/download")
        sys.exit(1)
    print(f"[OK] Config loaded. Backend: {data.get('backend_url', 'https://retail-vantag.com')}")
    print(f"[OK] API key: {data['api_key'][:8]}...")

if __name__ == "__main__":
    print("=" * 60)
    print("  Vantag Edge Agent v1.0.0")
    print("=" * 60)
    check_requirements()
    check_config()
    print("[*] Starting agent...")
    from agent.main import main
    main()
