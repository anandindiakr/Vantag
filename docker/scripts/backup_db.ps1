# ===========================================================================
# docker/scripts/backup_db.ps1
# PostgreSQL backup script — dumps the Vantag production database to a
# timestamped gzip file and prunes backups older than 7 days.
#
# Usage:
#   .\docker\scripts\backup_db.ps1
#
# Schedule nightly via Windows Task Scheduler:
#   Action: powershell.exe -NonInteractive -File "D:\...\docker\scripts\backup_db.ps1"
# ===========================================================================

param(
    [string]$ContainerName = "vantag-postgres-prod",
    [string]$DbName        = "vantag",
    [string]$DbUser        = "vantag",
    [int]   $RetainDays    = 7
)

$ROOT      = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$BackupDir = Join-Path $ROOT "backups"
$Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
$FileName  = "vantag_${DbName}_${Timestamp}.sql.gz"
$FilePath  = Join-Path $BackupDir $FileName

# ── Ensure backup directory exists ───────────────────────────────────────────
New-Item -ItemType Directory -Force $BackupDir | Out-Null

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Vantag — PostgreSQL Backup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Container : $ContainerName"
Write-Host "  Database  : $DbName"
Write-Host "  Output    : $FilePath"
Write-Host ""

# ── Run pg_dump inside the container and pipe through gzip ───────────────────
Write-Host "[1/3] Running pg_dump..." -ForegroundColor Yellow
try {
    docker exec $ContainerName pg_dump -U $DbUser $DbName | gzip > $FilePath
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed (exit code $LASTEXITCODE)" }
} catch {
    Write-Host "  ERROR: $_" -ForegroundColor Red
    exit 1
}

# ── Verify the gzip file is valid ─────────────────────────────────────────────
Write-Host "[2/3] Verifying backup integrity..." -ForegroundColor Yellow
$integrity = & gzip -t $FilePath 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Backup file is corrupt — $integrity" -ForegroundColor Red
    Remove-Item $FilePath -Force
    exit 1
}

$SizeMB = [math]::Round((Get-Item $FilePath).Length / 1MB, 2)
Write-Host "  OK — $FileName ($SizeMB MB)" -ForegroundColor Green

# ── Prune old backups ─────────────────────────────────────────────────────────
Write-Host "[3/3] Pruning backups older than $RetainDays days..." -ForegroundColor Yellow
$cutoff = (Get-Date).AddDays(-$RetainDays)
$removed = 0
Get-ChildItem $BackupDir -Filter "vantag_*.sql.gz" | Where-Object { $_.LastWriteTime -lt $cutoff } | ForEach-Object {
    Remove-Item $_.FullName -Force
    Write-Host "  Removed: $($_.Name)" -ForegroundColor DarkGray
    $removed++
}
if ($removed -eq 0) { Write-Host "  Nothing to prune." -ForegroundColor DarkGray }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Backup complete: $FileName" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
