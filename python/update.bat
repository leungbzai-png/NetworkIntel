@echo off
chcp 65001 >nul
cd /d %~dp0

echo ================================================
echo  NetworkIntel - One-click update
echo  (backup user data + rebuild exe)
echo ================================================
echo.
echo This script will:
echo   1. Backup sources.yaml + intel.db + current code
echo   2. Rebuild exe from current main_gui.py / gui_extensions.py / gui_map.py
echo.
set /p OK="Continue? (Y/N) "
if /I not "%OK%"=="Y" exit /b

echo.
echo === Step 1: Backup ===
call backup.bat

echo.
echo === Step 2: Rebuild exe ===
call build_gui_exe.bat
