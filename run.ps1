# Start the Portfolio Scanner backend (FastAPI) + frontend (Next.js) on Windows.
# Usage:  powershell -ExecutionPolicy Bypass -File .\run.ps1
# Logs:   backend\server.log / server.err.log, frontend\server.log / server.err.log
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- backend ---
Set-Location "$root\backend"
if (-not (Test-Path ".venv")) {
  Write-Host "Creating backend venv..." -ForegroundColor Cyan
  python -m venv .venv
  & ".\.venv\Scripts\python.exe" -m pip install --upgrade pip -q
  & ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
}
$env:DATA_MODE = if ($env:DATA_MODE) { $env:DATA_MODE } else { "auto" }
$env:ADVISOR_ENABLED = if ($env:ADVISOR_ENABLED) { $env:ADVISOR_ENABLED } else { "true" }
# No --reload: its file-watcher parent can die and orphan a child that keeps
# serving stale code on :8000. Restart via this script after code changes.
$backend = Start-Process -PassThru -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000" `
  -RedirectStandardOutput "$root\backend\server.log" `
  -RedirectStandardError "$root\backend\server.err.log" `
  -WindowStyle Hidden

# --- frontend ---
Set-Location "$root\frontend"
if (-not (Test-Path "node_modules")) {
  Write-Host "Installing frontend deps..." -ForegroundColor Cyan
  npm install
}
# NEXT_PUBLIC_API_BASE intentionally NOT set: the app is same-origin — Next
# proxies /api/* to :8000 server-side, which is what makes the phone tunnel
# (tunnel.ps1) and PWA work. Overriding it breaks remote access.
if (-not (Test-Path ".next")) {
  Write-Host "Building frontend..." -ForegroundColor Cyan
  npx next build
}
$frontend = Start-Process -PassThru -FilePath "cmd.exe" `
  -ArgumentList "/c", "npx next start -p 3000" `
  -RedirectStandardOutput "$root\frontend\server.log" `
  -RedirectStandardError "$root\frontend\server.err.log" `
  -WindowStyle Hidden

Write-Host ""
Write-Host "Backend  -> http://localhost:8000  (docs: /docs)" -ForegroundColor Green
Write-Host "Frontend -> http://localhost:3000" -ForegroundColor Green
Write-Host "Phone    -> run tunnel.ps1 for a public URL" -ForegroundColor Green
Write-Host "Logs     -> backend\server.err.log, frontend\server.err.log" -ForegroundColor DarkGray
Write-Host "Press Ctrl+C to stop both." -ForegroundColor DarkGray

# Stop both children when this script is interrupted.
try {
  Wait-Process -Id $backend.Id, $frontend.Id
} finally {
  foreach ($p in @($backend, $frontend)) {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  }
}
