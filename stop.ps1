# ============================================
#  VerdictAI-Now one-click stop
#  Stops: Frontend(5173) -> Backend(8787) -> Docker containers
#  Data preserved (PostgreSQL/Redis volumes kept).
#  Usage: stop
# ============================================

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-ListenerPid([int]$port) {
    try {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($conn) { return $conn.OwningProcess }
    } catch {}
    return $null
}

Write-Host ""
Write-Host "[1/3] Stopping Frontend (5173)..." -ForegroundColor Cyan
$fePid = Find-ListenerPid 5173
if ($fePid) {
    taskkill /PID $fePid /T /F 2>$null | Out-Null
    Write-Host "  Frontend stopped (PID $fePid)" -ForegroundColor Green
} else {
    Write-Host "  Frontend not running" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "[2/3] Stopping Backend (8787)..." -ForegroundColor Cyan
$bePid = Find-ListenerPid 8787
if ($bePid) {
    taskkill /PID $bePid /T /F 2>$null | Out-Null
    Write-Host "  Backend stopped (PID $bePid)" -ForegroundColor Green
} else {
    Write-Host "  Backend not running" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "[3/3] Stopping Docker containers (PostgreSQL + Redis)..." -ForegroundColor Cyan
Push-Location $Root
$null = docker compose stop 2>&1
$ok = ($LASTEXITCODE -eq 0)
Pop-Location
if ($ok) {
    Write-Host "  Containers stopped (data preserved)" -ForegroundColor Green
} else {
    Write-Host "  [NOTE] docker compose stop failed - Docker may not be running, ignore if so" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "All services stopped! To start again: dev" -ForegroundColor Green
Write-Host ""
