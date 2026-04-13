# ===========================================================================
# deploy.ps1 — One-command Vantag production deployment
#
# Run from the repo root:
#   .\deploy.ps1
#
# What it does:
#   1. Builds the React frontend with production API URL
#   2. Starts all Docker containers (postgres, mosquitto, backend, nginx, certbot)
#   3. Seeds the demo account
#   4. Verifies all services are healthy
# ===========================================================================

param(
    [string]$Domain    = "YOUR_DOMAIN",    # e.g. retailnazar.in
    [string]$ComposeFile = "docker\docker-compose.prod.yml"
)

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Vantag — Production Deploy" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# ── Preflight ─────────────────────────────────────────────────────────────────
if ($Domain -eq "YOUR_DOMAIN") {
    Write-Host "  ERROR: Set -Domain to your actual domain, e.g.:" -ForegroundColor Red
    Write-Host "         .\deploy.ps1 -Domain retailnazar.in" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path (Join-Path $ROOT ".env"))) {
    Write-Host "  ERROR: .env file not found. Copy .env.example → .env and fill in secrets." -ForegroundColor Red
    exit 1
}

# ── Step 1: Build frontend ────────────────────────────────────────────────────
Write-Host "[1/4] Building React frontend for https://$Domain ..." -ForegroundColor Yellow
$env:VITE_API_BASE_URL = "https://$Domain"
$env:VITE_WS_URL       = "wss://$Domain/ws"
Set-Location "$ROOT\frontend\web"
npm run build 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "  Frontend build FAILED." -ForegroundColor Red; exit 1 }
Write-Host "  Frontend built." -ForegroundColor Green
Set-Location $ROOT

# ── Step 2: Start containers ──────────────────────────────────────────────────
Write-Host "[2/4] Starting Docker containers..." -ForegroundColor Yellow
docker compose -f "$ROOT\$ComposeFile" up -d --build 2>&1
if ($LASTEXITCODE -ne 0) { Write-Host "  Docker start FAILED." -ForegroundColor Red; exit 1 }
Write-Host "  Containers started. Waiting 20s for health checks..." -ForegroundColor Green
Start-Sleep -Seconds 20

# ── Step 3: Seed demo account ─────────────────────────────────────────────────
Write-Host "[3/4] Seeding demo account..." -ForegroundColor Yellow
$env:PYTHONPATH = $ROOT
$env:DATABASE_URL = (Get-Content "$ROOT\.env" | Select-String "DATABASE_URL" | ForEach-Object { $_ -replace "DATABASE_URL=","" })
python -m backend.db.seed_demo 2>&1
Write-Host "  Seed done." -ForegroundColor Green

# ── Step 4: Health check ──────────────────────────────────────────────────────
Write-Host "[4/4] Verifying services..." -ForegroundColor Yellow
$health = docker compose -f "$ROOT\$ComposeFile" ps --format json 2>&1
docker compose -f "$ROOT\$ComposeFile" ps

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Deployment complete!" -ForegroundColor Green
Write-Host ""
Write-Host "  Site      : https://$Domain" -ForegroundColor White
Write-Host "  API docs  : https://$Domain/api/docs" -ForegroundColor White
Write-Host "  Demo login: demo@vantag.io / demo1234" -ForegroundColor Magenta
Write-Host ""
Write-Host "  SSL cert  : run docker\certbot\init-letsencrypt.sh first" -ForegroundColor DarkYellow
Write-Host "              if you haven't already." -ForegroundColor DarkYellow
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
