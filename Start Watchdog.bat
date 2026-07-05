@echo off
REM Double-click to boot Portfolio Scanner (backend + frontend + tunnel).
REM Safe to run after every reboot.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0start-all.ps1"
