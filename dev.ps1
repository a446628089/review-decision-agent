# ============================================
#  VerdictAI-Now single-terminal dev mode
#  One command: starts Docker(PostgreSQL+Redis)
#  -> auto-init pgvector + alembic + seed
#  -> backend(8787) + frontend(5173) in background
#  Logs stream into this terminal. Ctrl+C to stop all.
#
#  Usage:  dev            (with seed data)
#          dev -NoSeed    (skip seed data)
# ============================================

param(
    [switch]$NoSeed
)

# 注意：不用 $ErrorActionPreference="Stop"，
# 原生命令(docker/pnpm)的 stderr 会被 PowerShell 当成 ErrorRecord 抛异常，
# 导致脚本中断。统一用 $LASTEXITCODE 显式检查。
$ErrorActionPreference = "Continue"
# UTF-8 输出，避免中文乱码（Windows 默认 GBK）
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
$OutputEncoding = [System.Text.Encoding]::UTF8
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$BackendPy = Join-Path $BackendDir ".venv\Scripts\python.exe"

# Clean old log files
Remove-Item "$Root\dev-backend.log", "$Root\dev-backend-err.log", "$Root\dev-frontend.log", "$Root\dev-frontend-err.log" -Force -ErrorAction SilentlyContinue

function Write-Step($msg) {
    Write-Host ""
    Write-Host "$msg" -ForegroundColor Cyan
}
function Write-OK($msg) {
    Write-Host "  $msg" -ForegroundColor Green
}
function Write-Fail($msg) {
    Write-Host "  [ERROR] $msg" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------
Write-Step "[1/4] Checking Docker engine..."
$null = docker info 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Docker not running, starting Docker Desktop..." -ForegroundColor Yellow
    $dockerDesktop = @(
        "C:\Program Files\Docker\Docker\Docker Desktop.exe",
        "D:\develop\Docker\Docker Desktop.exe",
        "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($dockerDesktop) {
        Start-Process $dockerDesktop
    } else {
        Write-Fail "Docker Desktop not found. Start it manually, then re-run this script."
    }
    $waited = 0
    while ($waited -lt 90) {
        Start-Sleep -Seconds 3
        $waited += 3
        $null = docker info 2>&1
        if ($LASTEXITCODE -eq 0) { break }
    }
    $null = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Docker engine not ready in 90s"
    }
}
Write-OK "Docker engine ready"

# ------------------------------------------------------------
Write-Step "[2/4] Starting containers (PostgreSQL:15432 + Redis:6379)..."
Push-Location $Root
$null = docker compose up -d 2>&1
$composeOk = ($LASTEXITCODE -eq 0)
Pop-Location
if (-not $composeOk) { Write-Fail "docker compose up failed" }
Write-OK "Containers started"

# Wait for PostgreSQL to accept connections (healthcheck may lag)
Write-Host "  Waiting for PostgreSQL to become ready..." -ForegroundColor Yellow
$dbReady = $false
for ($i = 0; $i -lt 30; $i++) {
    $null = docker compose -f "$Root\docker-compose.yml" exec -T postgres pg_isready -U postgres 2>&1
    if ($LASTEXITCODE -eq 0) { $dbReady = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $dbReady) { Write-Fail "PostgreSQL not ready after 60s" }
Write-OK "PostgreSQL ready"

# ------------------------------------------------------------
Write-Step "[3/4] Initializing database (pgvector + alembic migrations)..."
# pgvector extension must exist BEFORE migrations (they use VECTOR type)
$null = docker compose -f "$Root\docker-compose.yml" exec -T postgres psql -U postgres -d yuan_meet -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1
if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to enable pgvector extension" }
Write-OK "pgvector extension enabled"

# Run alembic migrations (idempotent: no-op if already at head)
$env:PYTHONPATH = "."
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
Push-Location $BackendDir
& $BackendPy -m alembic upgrade head 2>&1 | ForEach-Object { "  $_" }
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Fail "alembic migration failed" }
Pop-Location
Write-OK "Database schema up to date"

# Seed data (idempotent: clears & re-inserts). Skip with -NoSeed
if (-not $NoSeed) {
    Write-Host "  Seeding demo data (3 meetings + 5 knowledge docs)..." -ForegroundColor Yellow
    Push-Location $BackendDir
    & $BackendPy seed_data.py 2>&1 | ForEach-Object { "  $_" }
    $seedOk = ($LASTEXITCODE -eq 0)
    Pop-Location
    if (-not $seedOk) { Write-Fail "seed_data.py failed" }
    Write-OK "Seed data loaded"
} else {
    Write-Host "  Skipping seed data (-NoSeed)" -ForegroundColor Yellow
}

# ------------------------------------------------------------
Write-Step "[4/4] Starting backend(8787) + frontend(5173) in background..."

# Backend: background process, logs to files
$backend = Start-Process -FilePath $BackendPy `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8787") `
    -WorkingDirectory $BackendDir `
    -RedirectStandardOutput "$Root\dev-backend.log" `
    -RedirectStandardError "$Root\dev-backend-err.log" `
    -WindowStyle Hidden -PassThru

# Frontend: background process, logs to files
$frontend = Start-Process -FilePath "pnpm.cmd" `
    -ArgumentList @("run", "dev") `
    -WorkingDirectory $FrontendDir `
    -RedirectStandardOutput "$Root\dev-frontend.log" `
    -RedirectStandardError "$Root\dev-frontend-err.log" `
    -WindowStyle Hidden -PassThru

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host " Services started! Press Ctrl+C to stop all." -ForegroundColor Green
Write-Host "  Backend : http://localhost:8787/docs" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

try {
    # Tail all 4 log files in real time (Ctrl+C interrupts)
    Get-Content "$Root\dev-backend.log", "$Root\dev-backend-err.log", "$Root\dev-frontend.log", "$Root\dev-frontend-err.log" -Wait -Tail 5 -ErrorAction SilentlyContinue
}
finally {
    Write-Host ""
    Write-Host "Stopping services..." -ForegroundColor Yellow

    # Frontend: pnpm.cmd spawns a process TREE (cmd -> node). taskkill /T kills the whole tree.
    if ($frontend) {
        taskkill /PID $frontend.Id /T /F 2>$null | Out-Null
    }
    # Backend: uvicorn single process, /T also safe.
    if ($backend) {
        taskkill /PID $backend.Id /T /F 2>$null | Out-Null
    }

    Write-Host "All services stopped" -ForegroundColor Green
    Write-Host "  Docker containers kept running (data preserved)." -ForegroundColor DarkGray
    Write-Host "  To stop them too:  docker compose -f `"$Root\docker-compose.yml`" stop" -ForegroundColor DarkGray
}
