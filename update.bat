@echo off
chcp 65001 >nul
title NetworkIntel - Update
cd /d E:\NetworkIntel\python

D:\Python\python.exe --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: D:\Python\python.exe not found
    pause
    exit /b 1
)

echo Checking dependencies...
D:\Python\python.exe -c "import yaml, requests, geoip2, apscheduler, textual, darkdetect" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies, please wait...
    D:\Python\python.exe -m pip install textual darkdetect APScheduler requests aiohttp geoip2 pyyaml
    echo.
)

D:\Python\python.exe do_update.py
pause
