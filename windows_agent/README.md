# Vantag Windows Edge Agent

A Windows background service that connects your IP cameras to the Vantag platform.

## Requirements

- Windows 10 or 11 (64-bit)
- Python 3.11+ (for running from source)
- OR: use the pre-built `VantagAgent.exe`

## Quick Start (from source)

```bash
cd vantag/windows_agent
pip install -r requirements.txt
python -m agent.main
```

## Build Standalone EXE

```bash
python build_exe.py
```

Output: `dist/VantagAgent/VantagAgent.exe`

## Configuration

Config is stored at: `%APPDATA%\Vantag\config.json`

First-run: opens your browser to the Vantag onboarding page automatically.

## Architecture

```
EdgeAgentService (main.py)
  ├── CameraWorker × N    — RTSP capture + YOLO inference threads
  ├── VantagMqttClient    — door control subscriber
  ├── VantagApiClient     — event + heartbeat poster
  └── VantagTrayIcon      — Windows system tray
```

## Supported Events

| Event | Description |
|-------|-------------|
| `sweep` | Product sweep/bulk theft detected |
| `dwell` | Person loitering >30s |
| `empty_shelf` | No shelf items visible for >60s |
| `tamper` | Camera obstructed or moved |
