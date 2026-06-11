@echo off
chcp 65001 >nul
title NetworkIntel
cd /d E:\NetworkIntel\python

D:\Python\python.exe -c "import textual" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    D:\Python\python.exe -m pip install textual darkdetect APScheduler requests aiohttp geoip2 pyyaml
)

D:\Python\python.exe main.py 2> ..\logs\startup_error.txt
if errorlevel 1 (
    echo.
    echo === ERROR ===
    type ..\logs\startup_error.txt
    echo.
    pause
)
