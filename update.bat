@echo off
chcp 65001 >nul
title NetworkIntel - Update
cd /d "%~dp0python"

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: python not found on PATH
    pause
    exit /b 1
)

echo Checking dependencies...
python -c "import yaml, requests, geoip2, apscheduler, textual, darkdetect" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies, please wait...
    python -m pip install textual darkdetect APScheduler requests aiohttp geoip2 pyyaml
    echo.
)

python do_update.py
pause
