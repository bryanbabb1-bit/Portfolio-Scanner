# Docker setup on Windows (do later)

`docker compose up --build` needs Docker Desktop, which on **Windows Home**
requires **WSL2**. The automated install failed here because WSL2 wasn't
installed and Docker Desktop needs **admin elevation + a reboot** — steps that
can't run headlessly. Do this when you have a moment:

## Steps (run in an **elevated** PowerShell — "Run as Administrator")

```powershell
# 1. Install WSL2 (Windows Subsystem for Linux)
wsl --install
```

**Reboot.** Then, again in an elevated PowerShell:

```powershell
# 2. Install Docker Desktop
winget install -e --id Docker.DockerDesktop
```

**Reboot / launch Docker Desktop once** so it finishes first-run setup (it will
enable the WSL2 backend automatically).

## Then run the app with Docker

```bash
cd portfolio-scanner
git checkout claude/stock-portfolio-hub-m3mj1g
docker compose up --build
```

- App: http://localhost:3000
- API: http://localhost:8000/docs

Stop with `Ctrl+C`, or `docker compose down`.

---

## Don't want Docker? You don't need it.

The app runs natively — Python 3.14 + Node 24 are already installed:

```powershell
# from the repo root
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

(macOS/Linux/Git Bash: `./run.sh`.) Same result: backend on :8000, frontend on
:3000.
