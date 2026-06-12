# Vantag Windows Edge Agent

Runs on a store Windows PC. Connects your LAN cameras to the Vantag cloud platform.

## What it does
- Scans your local network (192.168.x.x) for IP cameras automatically
- Streams RTSP video and runs AI (YOLOv8) to detect: shoplifting, loitering, empty shelves, camera tampering
- Sends incidents + thumbnails to your Vantag dashboard in real-time
- Receives commands (door lock/unlock) via MQTT from the dashboard

---

## Option A — Test without building .exe (Quickest for LAN testing)

**Requirements:** Python 3.11 or 3.12, Windows 10/11 64-bit, connected to the store LAN

```
1. Get your API key:
   → Log in to https://retail-vantag.com → Install Edge Agent page → Copy API Key

2. Copy the template config:
   copy config.template.json config.json

3. Edit config.json — set api_key:
   "api_key": "paste-your-key-here"

4. Double-click setup.bat
   (OR run: pip install -r requirements.txt && python run_agent.py)
```

The agent will:
- Register itself with the backend (auto-assigns agent_id)
- Scan your LAN for cameras → results appear in Dashboard → Agent Status page
- Show a shield icon in your Windows taskbar tray

---

## Option B — Build standalone .exe (for store deployment)

**Requirements:** Python 3.11 or 3.12

```bash
pip install pyinstaller pillow
python build_exe.py
```

Output: `dist/VantagAgent/VantagAgent.exe`

To distribute to a store:
1. Copy `config.template.json` → rename to `config.json` in `dist/VantagAgent/`
2. Edit `config.json` — set `api_key`
3. ZIP the `dist/VantagAgent/` folder
4. Staff at the store: extract ZIP and double-click `VantagAgent.exe`

---

## Configuration (`config.json`)

| Field | Description |
|-------|-------------|
| `api_key` | **Required.** Get from retail-vantag.com/download |
| `agent_id` | Leave blank — assigned automatically on first run |
| `backend_url` | `https://retail-vantag.com` (default, do not change) |
| `mqtt_host` | `retail-vantag.com` (default) |
| `cameras` | Leave blank — auto-discovered from LAN scan |
| `inference_device` | `cpu` (default), `cuda` if GPU available |
| `inference_fps` | Frames per second for AI (default 5, reduce to 2 on slow PCs) |
| `confidence_threshold` | 0.6 = 60% confidence required to fire an event |

---

## Logs

Location: `%APPDATA%\Vantag\agent.log`

Open log in PowerShell: `Get-Content "$env:APPDATA\Vantag\agent.log" -Wait`

---

## Architecture

```
VantagAgent (main.py)
  ├── Discovery (discovery.py)    — WS-Discovery + TCP :554 scan → reports to backend
  ├── CameraWorker × N            — RTSP capture + YOLOv8 inference per camera
  ├── VantagApiClient             — POST events / heartbeat / discovered cameras
  ├── VantagMqttClient            — Subscribes to door control commands
  └── VantagTrayIcon              — Windows system tray (start/stop/quit)
```

## Detected Events

| Event | How it triggers |
|-------|-----------------|
| `shoplifting` | Person near high-value item for >2 seconds |
| `restricted_zone` | Person stationary in zone for >30 seconds |
| `inventory_movement` | No shelf items detected for >60 seconds |
| `camera_tamper` | Camera blocked or moved (no objects detected) |
