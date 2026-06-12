# Vantag Edge Agent

A small Python program that runs on your local PC / tablet / Raspberry Pi
and connects your LAN IP cameras to Vantag cloud.

## Install & run

### Windows
```powershell
.\install.ps1
```

### Linux / Mac / Raspberry Pi
```bash
./install.sh
```

## What it does
1. Asks you for your Vantag Cloud URL + Tenant ID (shown in your dashboard Install page)
2. Saves them to `~/.vantag/config.json`
3. Scans your local network (192.168.x.x) for IP cameras (RTSP port 554)
4. Registers discovered cameras with your Vantag cloud account
5. Sends heartbeat every 30s so the dashboard shows "Edge Online"

## Requirements
- Python 3.9 or newer
- Internet connection
- Cameras on the same LAN as this machine

## Security
- Video never leaves your network — only events + snapshots are uploaded
- Tenant ID is used as an API key; treat it like a password
