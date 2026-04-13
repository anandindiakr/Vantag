# start.ps1 - One-command Vantag startup
# Run: cd "D:\AI Algo\Collaterals\Profiles\Retail Nazar\vantag" ; .\start.ps1

$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

# Email credentials
$env:PYTHONPATH        = $ROOT
$env:VANTAG_SMTP_HOST  = "smtp.gmail.com"
$env:VANTAG_SMTP_PORT  = "587"
$env:VANTAG_SMTP_USER  = "anandindiakr@gmail.com"
$env:VANTAG_SMTP_PASS  = "YOUR_GMAIL_APP_PASSWORD"
$env:VANTAG_EMAIL_FROM = "Vantag <anandindiakr@gmail.com>"

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  Vantag - Starting up" -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan

# 1. Docker containers
Write-Host "[1/3] Starting Docker containers..." -ForegroundColor Yellow
docker start vantag-postgres vantag-mosquitto 2>$null
Start-Sleep -Seconds 2
Write-Host "      OK" -ForegroundColor Green

# 2. Seed demo account
Write-Host "[2/4] Seeding demo account..." -ForegroundColor Yellow
python -m backend.db.seed_demo 2>&1
Write-Host "      Done." -ForegroundColor Green

# 3. Backend
Write-Host "[3/4] Starting backend on :8800..." -ForegroundColor Yellow
$backend = Start-Process "python" `
    -ArgumentList "-m","uvicorn","backend.api.main:app","--host","0.0.0.0","--port","8800" `
    -WorkingDirectory $ROOT -PassThru -WindowStyle Normal
Write-Host "      Backend PID $($backend.Id)" -ForegroundColor Green
Start-Sleep -Seconds 4

# 4. Frontend
Write-Host "[4/4] Starting frontend on :3000..." -ForegroundColor Yellow
$frontend = Start-Process "npx" `
    -ArgumentList "vite","--port","3000" `
    -WorkingDirectory "$ROOT\frontend\web" -PassThru -WindowStyle Normal
Write-Host "      Frontend PID $($frontend.Id)" -ForegroundColor Green

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  OPEN: http://localhost:3000" -ForegroundColor Green
Write-Host "  Login: demo@vantag.io / demo1234" -ForegroundColor Magenta
Write-Host "  Close this window to stop all servers" -ForegroundColor DarkGray
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host ""

Wait-Process -Id $backend.Id -ErrorAction SilentlyContinue
Stop-Process -Id $frontend.Id -ErrorAction SilentlyContinue