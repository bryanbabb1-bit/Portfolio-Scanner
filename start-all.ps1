# Portfolio Scanner — one-click boot. Starts the backend, the frontend, and the
# permanent Cloudflare tunnel so the laptop dashboard AND the phone app both
# work. Run this after every reboot (double-click "Start Watchdog" on the
# desktop, or run this file).
#
# First run only: the tunnel window opens your browser to authorize Cloudflare
# (pick trueforecasting.app). After that it's fully automatic.

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = "$root\backend\.venv\Scripts\python.exe"

function Stop-Port($port) {
  Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -Confirm:$false } catch {} }
}

Write-Host "Starting Portfolio Scanner..." -ForegroundColor Cyan

# --- backend (FastAPI :8000) ---
Stop-Port 8000
Start-Process -WindowStyle Hidden -FilePath $py `
  -ArgumentList "-m", "uvicorn", "app.main:app", "--port", "8000" `
  -WorkingDirectory "$root\backend" `
  -RedirectStandardOutput "$root\backend\server.log" `
  -RedirectStandardError "$root\backend\server.err.log"
Write-Host "  backend  -> starting on :8000" -ForegroundColor DarkGray

# --- frontend (Next :3000) — build once if never built ---
if (-not (Test-Path "$root\frontend\.next")) {
  Write-Host "  frontend -> building (first run, ~30s)..." -ForegroundColor DarkGray
  Push-Location "$root\frontend"; npx next build | Out-Null; Pop-Location
}
Stop-Port 3000
Start-Process -WindowStyle Hidden -FilePath "cmd.exe" `
  -ArgumentList "/c", "npx next start -p 3000" `
  -WorkingDirectory "$root\frontend" `
  -RedirectStandardOutput "$root\frontend\server.log" `
  -RedirectStandardError "$root\frontend\server.err.log"
Write-Host "  frontend -> starting on :3000" -ForegroundColor DarkGray

# --- tunnel (watchdog.trueforecasting.app -> :3000) ---
# Retire any old quick tunnel, then run the permanent named one hidden with a
# log (creates it the first time if needed). Silent so it can auto-start at
# login without popping a window.
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Process -WindowStyle Hidden -FilePath "powershell.exe" `
  -ArgumentList "-ExecutionPolicy", "Bypass", "-File", "$root\watchdog-tunnel.ps1" `
  -RedirectStandardOutput "$root\tunnel.log" `
  -RedirectStandardError "$root\tunnel.err.log"
Write-Host "  tunnel   -> starting watchdog.trueforecasting.app" -ForegroundColor DarkGray

Start-Sleep -Seconds 12
Write-Host ""
$b = try { (Invoke-WebRequest -UseBasicParsing http://localhost:8000/api/health -TimeoutSec 5).StatusCode } catch { "down" }
$f = try { (Invoke-WebRequest -UseBasicParsing http://localhost:3000 -TimeoutSec 5).StatusCode } catch { "down" }
$p = try { (Invoke-WebRequest -UseBasicParsing https://watchdog.trueforecasting.app/api/health -TimeoutSec 12).StatusCode } catch { "connecting" }
Write-Host "Backend  http://localhost:8000              [$b]" -ForegroundColor Green
Write-Host "Frontend http://localhost:3000              [$f]" -ForegroundColor Green
Write-Host "Phone    https://watchdog.trueforecasting.app  [$p]" -ForegroundColor Green
Write-Host ""
Write-Host "All set. You can close this window." -ForegroundColor Cyan
Start-Sleep -Seconds 4
