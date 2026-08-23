@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher not found. Install Python 3.13 from https://python.org/ and retry.
  exit /b 1
)

py -3.13 -m venv .venv
if errorlevel 1 exit /b 1

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -c constraints.txt -e vendor\diplomacy
python -m pip install -c constraints.txt -e ".[dev]"
if errorlevel 1 exit /b 1

echo.
echo Setup complete. Run run-windows.bat to start Diplomacy.
