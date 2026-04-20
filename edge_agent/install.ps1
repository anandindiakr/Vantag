# Vantag Edge Agent installer — Windows PowerShell
Write-Host "=============================================="
Write-Host "  Vantag Edge Agent — Installer"
Write-Host "=============================================="
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "[!] Python not found. Please install Python 3.9+ from python.org first."
    exit 1
}
python -m pip install --user requests --quiet
Write-Host "[OK] Dependencies installed"
python (Join-Path $PSScriptRoot "vantag_agent.py")
