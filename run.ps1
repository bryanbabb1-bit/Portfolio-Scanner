# Start the Portfolio Scanner backend (FastAPI) + frontend (Next.js) on Windows.
# Usage:  powershell -ExecutionPolicy Bypass -File .\run.ps1
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
$backend = Start-Process -PassThru -NoNewWindow -FilePath ".\.venv\Scripts\python.exe" `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"

# --- frontend ---
Set-Location "$root\frontend"
if (-not (Test-Path "node_modules")) {
  Write-Host "Installing frontend deps..." -ForegroundColor Cyan
  npm install
}
$env:NEXT_PUBLIC_API_BASE = if ($env:NEXT_PUBLIC_API_BASE) { $env:NEXT_PUBLIC_API_BASE } else { "http://localhost:8000" }
$frontend = Start-Process -PassThru -NoNewWindow -FilePath "npm" -ArgumentList "run", "dev"

Write-Host ""
Write-Host "Backend  -> http://localhost:8000  (docs: /docs)" -ForegroundColor Green
Write-Host "Frontend -> http://localhost:3000" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop both." -ForegroundColor DarkGray

# Stop both children when this script is interrupted.
try {
  Wait-Process -Id $backend.Id, $frontend.Id
} finally {
  foreach ($p in @($backend, $frontend)) {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  }
}
