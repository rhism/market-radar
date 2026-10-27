@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0market_radar.py"
    pause
    exit /b 0
)
python "%~dp0market_radar.py"
pause
