# One-time elevated upgrade of cloudflared 2025.8.1 -> 2026.7.1, in place.
# Run ELEVATED (it writes to Program Files). Restores the tunnel when done.
$ErrorActionPreference = "Continue"
$cf   = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$new  = "C:\Users\bryan\AppData\Local\Temp\claude\C--Users-bryan\b6e0fa19-4e73-4d62-a3d6-21bb7e8cdf96\scratchpad\cloudflared-new.exe"
$root = "C:\Users\bryan\portfolio-scanner"

if (-not (Test-Path $new)) { Write-Host "Staged binary missing: $new" -ForegroundColor Red; Start-Sleep 6; exit 1 }

Write-Host "Stopping cloudflared..." -ForegroundColor Cyan
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "Backing up + replacing binary..." -ForegroundColor Cyan
Copy-Item $cf "$cf.2025.8.1.bak" -Force
Copy-Item $new $cf -Force
Write-Host ("Installed: " + ((& $cf --version 2>&1 | Select-Object -First 1))) -ForegroundColor Green

Write-Host "Restarting tunnel..." -ForegroundColor Cyan
Start-Process -WindowStyle Hidden -FilePath "powershell.exe" `
  -ArgumentList "-ExecutionPolicy","Bypass","-File","$root\watchdog-tunnel.ps1" `
  -RedirectStandardOutput "$root\tunnel.log" -RedirectStandardError "$root\tunnel.err.log"
Start-Sleep -Seconds 12
$p = try { (Invoke-WebRequest -UseBasicParsing https://watchdog.trueforecasting.app/api/health -TimeoutSec 15).StatusCode } catch { "connecting" }
Write-Host "Phone URL health: [$p]" -ForegroundColor Green
Write-Host "Done. You can close this window." -ForegroundColor Cyan
Start-Sleep -Seconds 5
