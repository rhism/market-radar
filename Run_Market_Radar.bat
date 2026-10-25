@echo off
setlocal
cd /d "%~dp0"
where pyw >nul 2>&1
if not errorlevel 1 (
    start "Market Radar" pyw -3 "%~dp0market_radar.py"
    exit /b 0
)
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "Market Radar" pythonw "%~dp0market_radar.py"
    exit /b 0
)
echo Python for Windows was not found.
echo Install Python 3.11 or newer from https://www.python.org/downloads/windows/
pause
