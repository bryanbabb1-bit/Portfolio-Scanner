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
  Write-Host "No cert.pem found. Run this first (one-time, opens browser):" -ForegroundColor Yellow
  Write-Host "  & `"$cf`" tunnel login" -ForegroundColor Cyan
  exit 1
}

# Create the tunnel once (idempotent — skips if it already exists).
$existing = & $cf tunnel list 2>$null | Select-String $name
if (-not $existing) {
  Write-Host "Creating tunnel '$name'..." -ForegroundColor Cyan
  & $cf tunnel create $name
  Write-Host "Routing DNS $hostname -> tunnel..." -ForegroundColor Cyan
  & $cf tunnel route dns $name $hostname
}

# Resolve the tunnel's credentials file (named <UUID>.json in ~/.cloudflared).
$uuid = (& $cf tunnel list --output json | ConvertFrom-Json |
  Where-Object { $_.name -eq $name } | Select-Object -First 1).id
$credFile = "$cfgDir\$uuid.json"

# Write the ingress config each run (cheap, keeps it correct).
@"
tunnel: $uuid
credentials-file: $credFile
ingress:
  - hostname: $hostname
    service: http://localhost:3000
  - service: http_status:404
"@ | Set-Content -Encoding utf8 "$cfgDir\config.yml"

Write-Host ""
Write-Host "Backend will be reachable at https://$hostname" -ForegroundColor Green
Write-Host "Keep this window open. Ctrl+C to stop." -ForegroundColor DarkGray
& $cf tunnel run $name
