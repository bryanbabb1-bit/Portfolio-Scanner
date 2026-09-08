# Keep the desk alive.
#
# WHY THIS EXISTS. The backend died at 09:07 on Saturday 5 September 2026 with
# no traceback -- the log simply stops mid-request -- and nothing brought it
# back. It was down until Monday evening, when Bryan noticed the app was dead.
# The only scheduled trigger was AT LOGON, and the machine had been up for
# eleven days, so nothing was ever going to run.
#
# It cost nothing that week: the market was shut the whole time (weekend, then
# Labor Day). Had it happened on a Wednesday, the sleeve would have carried a
# live position through two sessions with no stop being watched, and issued no
# tickets while the market ran without it. That is the whole product failing
# silently, which is worse than it failing loudly.
#
# This is deliberately NOT start-all.ps1 on a timer. That script stops and
# restarts both servers every time it runs; on a ten-minute schedule it would
# bounce a perfectly healthy desk all day. This only ever starts what is
# actually down, and says nothing when everything is fine.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$log  = "$root\ensure-up.log"

function Note($msg) {
  "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" | Add-Content -Path $log -Encoding utf8
}

function Test-Port($port) {
  [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

# A port can be held open by a process that has stopped answering, so the
# backend is checked by asking it a question rather than by looking at a socket.
function Test-Backend {
  if (-not (Test-Port 8000)) { return $false }
  try {
    $r = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -TimeoutSec 8 -UseBasicParsing
    return $r.StatusCode -eq 200
  } catch { return $false }
}

if (-not (Test-Backend)) {
  Note "backend down -> starting"
  # Free the port first: a hung process still holding :8000 would block the
  # replacement and leave the desk down with a listener that answers nothing.
  Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { try { Stop-Process -Id $_.OwningProcess -Force -Confirm:$false } catch {} }
  # Roll the log rather than truncating it. server.log is the only record of
  # how the last one died, and -RedirectStandardOutput overwrites.
  if (Test-Path "$root\backend\server.log") {
    Move-Item "$root\backend\server.log" `
      "$root\backend\server.log.$(Get-Date -Format 'yyyy-MM-dd-HHmm')" -Force -ErrorAction SilentlyContinue
  }
  Start-Process -WindowStyle Hidden -FilePath "$root\backend\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","app.main:app","--port","8000" `
    -WorkingDirectory "$root\backend" `
    -RedirectStandardOutput "$root\backend\server.log" `
    -RedirectStandardError  "$root\backend\server.err.log"
}

if (-not (Test-Port 3000)) {
  Note "frontend down -> starting"
  Start-Process -WindowStyle Hidden -FilePath "cmd.exe" `
    -ArgumentList "/c","node_modules\.bin\next.cmd start -p 3000 >> ..\frontend.log 2>&1" `
    -WorkingDirectory "$root\frontend"
}

# The tunnel is what makes the phone work; a dead tunnel is a dead app on the
# device even while both servers are healthy on the desk.
if (-not (Get-Process -Name cloudflared -ErrorAction SilentlyContinue)) {
  Note "tunnel down -> starting"
  Start-Process -WindowStyle Hidden -FilePath "cloudflared" `
    -ArgumentList "tunnel","run","watchdog" `
    -WorkingDirectory $root `
    -RedirectStandardOutput "$root\tunnel.log" `
    -RedirectStandardError  "$root\tunnel.err.log" -ErrorAction SilentlyContinue
}

# Keep the log from growing without bound: it only ever records failures, so
# it should stay short for years.
if ((Test-Path $log) -and (Get-Item $log).Length -gt 200KB) {
  Get-Content $log -Tail 500 | Set-Content $log -Encoding utf8
}
