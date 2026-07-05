# Permanent named Cloudflare tunnel: watchdog.trueforecasting.app -> your PC's
# Next frontend on :3000 (which proxies /api/* to FastAPI on :8000). This is
# the stable URL the native app talks to.
#
# ONE-TIME, do this first (opens your browser, ~60s):
#   & "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel login
#   -> pick trueforecasting.app. Creates ~/.cloudflared/cert.pem.
#
# Then run THIS script. It creates the tunnel + DNS record the first time and
# runs it every time after. Leave it running (or install as a service) so the
# phone can always reach the backend while your PC is on.

$ErrorActionPreference = "Stop"
$cf = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$hostname = "watchdog.trueforecasting.app"
$name = "watchdog"
$cfgDir = "$HOME\.cloudflared"

if (-not (Test-Path "$cfgDir\cert.pem")) {
  Write-Host "First-time setup: opening your browser to authorize Cloudflare." -ForegroundColor Cyan
  Write-Host "In the browser, pick 'trueforecasting.app' and click Authorize." -ForegroundColor Cyan
  & $cf tunnel login
  if (-not (Test-Path "$cfgDir\cert.pem")) {
    Write-Host "Login didn't complete (no cert.pem). Re-run this script." -ForegroundColor Yellow
    exit 1
  }
}

# Create the tunnel once (idempotent — skips if it already exists).
$existing = & $cf tunnel list 2>$null | Select-String $name
if (-not $existing) {
  Write-Host "Creating tunnel '$name'..." -ForegroundColor Cyan
  & $cf tunnel create $name
  Write-Host "Routing DNS $hostname -> tunnel..." -ForegroundColor Cyan
  & $cf tunnel route dns $name $hostname
}

# Run the named tunnel with an inline route to the frontend. No config.yml —
# the DNS CNAME already points $hostname at this tunnel, and --url avoids
# Windows-path escaping bugs in a config file.
Write-Host ""
Write-Host "Serving https://$hostname  ->  http://localhost:3000" -ForegroundColor Green
Write-Host "Keep this window open. Ctrl+C to stop." -ForegroundColor DarkGray
& $cf tunnel run --url http://localhost:3000 $name
