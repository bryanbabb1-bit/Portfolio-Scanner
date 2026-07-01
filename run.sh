#!/usr/bin/env bash
# Start both the backend (FastAPI) and frontend (Next.js) for local dev.
# Cross-platform: works on Linux/macOS (.venv/bin) and Git Bash on Windows
# (.venv/Scripts). On Windows PowerShell, use run.ps1 instead.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pick a python launcher that exists on this platform.
PY="python3"; command -v "$PY" >/dev/null 2>&1 || PY="python"

# --- backend ---
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
# Windows venvs put executables in Scripts/, POSIX in bin/.
if [ -d .venv/Scripts ]; then VBIN=".venv/Scripts"; else VBIN=".venv/bin"; fi
if [ ! -f "$VBIN/uvicorn" ] && [ ! -f "$VBIN/uvicorn.exe" ]; then
  "$VBIN/python" -m pip install -q --upgrade pip
  "$VBIN/python" -m pip install -q -r requirements.txt
fi
"$VBIN/python" -m uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

# --- frontend ---
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then npm install; fi
npm run dev &
FRONTEND_PID=$!

trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT
echo "Backend  -> http://localhost:8000  (docs: /docs)"
echo "Frontend -> http://localhost:3000"
wait
