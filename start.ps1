# ============================================================
#  Vantag - Start all services
#  Run: cd "D:\AI Algo\Collaterals\Profiles\Retail Nazar\vantag" ; .\start.ps1
# ============================================================

$ROOT = "D:\AI Algo\Collaterals\Profiles\Retail Nazar\vantag"

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  Vantag - Starting services via pm2"  -ForegroundColor Cyan
Write-Host "=======================================" -ForegroundColor Cyan

# 1. Docker containers
Write-Host "[1/3] Starting Docker containers..." -ForegroundColor Yellow
docker start vantag-postgres vantag-mosquitto 2>$null
Start-Sleep -Seconds 2
Write-Host "      OK" -ForegroundColor Green

# 2. Seed demo account
Write-Host "[2/3] Seeding demo account..." -ForegroundColor Yellow
$env:PYTHONPATH = $ROOT
python -m backend.db.seed_demo 2>&1 | Select-Object -Last 1
Write-Host "      Done" -ForegroundColor Green

# 3. Start / restart via pm2
Write-Host "[3/3] Starting backend + frontend via pm2..." -ForegroundColor Yellow
Set-Location $ROOT
pm2 start ecosystem.config.js --update-env 2>&1 | Where-Object { $_ -match "online|error|WARN" }
pm2 save 2>$null

Write-Host ""
Write-Host "=======================================" -ForegroundColor Cyan
Write-Host "  All services running!" -ForegroundColor Green
Write-Host ""
Write-Host "  Dashboard : http://localhost:3000"  -ForegroundColor White
Write-Host "  API docs  : http://localhost:8800/docs" -ForegroundColor White
Write-Host "  Login     : demo@vantag.io / demo1234" -ForegroundColor Magenta
Write-Host ""
Write-Host "  pm2 status  -> run: pm2 status"      -ForegroundColor DarkGray
Write-Host "  pm2 logs    -> run: pm2 logs"         -ForegroundColor DarkGray
Write-Host "  pm2 stop    -> run: pm2 stop all"     -ForegroundColor DarkGray
Write-Host "=======================================" -ForegroundColor Cyan