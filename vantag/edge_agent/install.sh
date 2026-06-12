#!/bin/bash
# Vantag Edge Agent installer — Linux / Mac
set -e
echo "=============================================="
echo "  Vantag Edge Agent — Installer"
echo "=============================================="
command -v python3 >/dev/null 2>&1 || { echo "[!] Python 3 not found. Install Python 3.9+ first."; exit 1; }
python3 -m pip install --user requests --quiet
echo "[✓] Dependencies installed"
python3 "$(dirname "$0")/vantag_agent.py"
