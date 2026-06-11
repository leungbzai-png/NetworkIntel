@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d %~dp0

echo ================================================
echo  NetworkIntel - Backup user data
echo ================================================
echo.

if not exist ..\backups mkdir ..\backups

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"

set "TARGET=..\backups\backup_!STAMP!"
mkdir "!TARGET!"

echo [1/3] Backing up sources.yaml ...
if exist ..\configs\sources.yaml (
    copy /Y ..\configs\sources.yaml "!TARGET!\sources.yaml" >nul
    echo   OK
) else (
    echo   skipped (not found)
)

echo [2/3] Backing up intel.db (this may take a while) ...
if exist ..\live\intel.db (
    copy /Y ..\live\intel.db "!TARGET!\intel.db" >nul
    echo   OK
) else (
    echo   skipped (not found)
)

echo [3/3] Backing up source code ...
xcopy /S /I /Q /Y "*.py" "!TARGET!\code\" >nul

echo.
echo  Backup folder: !TARGET!
echo.
echo  Tip: also copy this folder to a USB / cloud drive for safety
pause