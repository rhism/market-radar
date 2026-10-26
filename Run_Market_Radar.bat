@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 goto use_py
where python >nul 2>&1
if not errorlevel 1 goto use_python

echo Python for Windows was not found.
echo Install Python 3.11 or newer from https://www.python.org/downloads/windows/
pause
exit /b 1

:use_py
py -3 -c "import customtkinter" >nul 2>&1
if errorlevel 1 (
    echo Installing Market Radar UI dependency...
    py -3 -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 goto install_failed
)
where pyw >nul 2>&1
if not errorlevel 1 (
    start "Market Radar" pyw -3 "%~dp0market_radar.py"
) else (
    start "Market Radar" py -3 "%~dp0market_radar.py"
)
exit /b 0

:use_python
python -c "import customtkinter" >nul 2>&1
if errorlevel 1 (
    echo Installing Market Radar UI dependency...
    python -m pip install -r "%~dp0requirements.txt"
    if errorlevel 1 goto install_failed
)
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "Market Radar" pythonw "%~dp0market_radar.py"
) else (
    start "Market Radar" python "%~dp0market_radar.py"
)
exit /b 0

:install_failed
echo.
echo Could not install CustomTkinter. Check your internet connection and Python pip setup.
echo You can also run: py -3 -m pip install -r requirements.txt
pause
exit /b 1
