@echo off
chcp 65001 >nul
title NetworkIntel - Build EXE
cd /d E:\NetworkIntel\python

echo Building NetworkIntel.exe ...
echo This may take 5-10 minutes on first run.
echo.

D:\Python\python.exe -m pip install pyinstaller >nul 2>&1

D:\Python\python.exe -m PyInstaller ^
    --onefile ^
    --name NetworkIntel ^
    --add-data "..\configs;configs" ^
    --hidden-import textual ^
    --hidden-import apscheduler ^
    --hidden-import geoip2 ^
    --hidden-import darkdetect ^
    --hidden-import yaml ^
    --collect-all textual ^
    --noconsole ^
    main.py

echo.
if exist dist\NetworkIntel.exe (
    echo SUCCESS: dist\NetworkIntel.exe
) else (
    echo FAILED. Check errors above.
)
echo.
pause
