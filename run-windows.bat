@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Environment missing. Run setup-windows.bat first.
  exit /b 1
)
.venv\Scripts\python.exe -m diplomacy_app
