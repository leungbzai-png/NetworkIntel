@echo off
chcp 65001 >nul
title NetworkIntel
cd /d "%~dp0python"

python -c "import textual" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    python -m pip install textual darkdetect APScheduler requests aiohttp geoip2 pyyaml
)

if not exist "..\logs" mkdir "..\logs"
python main.py 2> ..\logs\startup_error.txt
if errorlevel 1 (
    echo.
    echo === ERROR ===
    type ..\logs\startup_error.txt
    echo.
    pause
)
