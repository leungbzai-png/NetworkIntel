@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d %~dp0

set "VERSION_TAG="
for /f "tokens=2 delims==" %%i in ('findstr /B "APP_VERSION" main_gui.py') do (
    set "VERSION_TAG=%%i"
)
set "VERSION_TAG=!VERSION_TAG: =!"
set "VERSION_TAG=!VERSION_TAG:"=!"

echo ================================================
echo  NetworkIntel - Build EXE
echo  Version: !VERSION_TAG!
echo ================================================
echo.

echo [1/4] Checking deps ...
python -m pip install --upgrade --quiet pyinstaller PySide6 || (
    echo FAILED to install deps & pause & exit /b 1
)

echo [2/4] Backing up previous exe (if any) ...
if exist dist\NetworkIntel.exe (
    if not exist dist_backup mkdir dist_backup
    for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set "TODAY=%%a-%%b-%%c"
    for /f "tokens=1-2 delims=: " %%a in ('time /t') do set "NOW=%%a%%b"
    copy /Y dist\NetworkIntel.exe dist_backup\NetworkIntel_!TODAY!_!NOW!.exe >nul
    echo   backed up to dist_backup\
)

echo [3/4] Building (may take 3-8 minutes for first time with QtWebEngine) ...
python -m PyInstaller --noconfirm --clean --onefile --windowed --name NetworkIntel ^
  --collect-submodules apscheduler ^
  --collect-submodules tzlocal ^
  --collect-submodules yaml ^
  --collect-all PySide6.QtWebEngineWidgets ^
  --collect-all PySide6.QtWebEngineCore ^
  --hidden-import gui_extensions ^
  --hidden-import gui_map ^
  --hidden-import datasources.plugins.geoip ^
  --hidden-import datasources.plugins.ip2asn ^
  --hidden-import datasources.plugins.rir_delegated ^
  --hidden-import datasources.plugins.rpki ^
  --hidden-import datasources.plugins.cloud_aws ^
  --hidden-import datasources.plugins.cloud_azure ^
  --hidden-import datasources.plugins.cloud_gcp ^
  --hidden-import datasources.plugins.cloud_cloudflare ^
  --hidden-import datasources.plugins.cloud_hetzner ^
  --hidden-import datasources.plugins.cloud_vultr ^
  --hidden-import datasources.plugins.tor_exits ^
  --hidden-import datasources.plugins.vpn_x4bnet ^
  --hidden-import datasources.plugins.spamhaus ^
  --hidden-import datasources.plugins.firehol ^
  --hidden-import datasources.plugins.abusech ^
  --hidden-import datasources.plugins.emerging_threats ^
  --hidden-import datasources.plugins.peeringdb ^
  main_gui.py

echo.
if exist dist\NetworkIntel.exe (
    echo [4/4] DONE! exe path: %~dp0dist\NetworkIntel.exe
    echo.
    for %%I in (dist\NetworkIntel.exe) do echo  Size: %%~zI bytes
    echo  Right-click the exe -^> Send to -^> Desktop shortcut
) else (
    echo [4/4] BUILD FAILED, check errors above
)
echo.
pause
