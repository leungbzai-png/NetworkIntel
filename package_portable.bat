@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title NetworkIntel - Package Portable Zip
cd /d "%~dp0"

rem ============================================================
rem  NetworkIntel - 打包 Portable 发布 zip（v0.2.0+）
rem  顶层目录： NetworkIntel-v<VERSION>-windows-x64-portable\
rem  产物：
rem    dist\NetworkIntel-v<VERSION>-windows-x64-portable.zip
rem    E:\Backup\Releases\NetworkIntel\NetworkIntel-v<VERSION>-windows-x64-portable.zip
rem  内容：GUI exe + 配置模板(.example) + .env.example + RUNNING.txt + 关键文档
rem  注意：exe / dist / zip 已被 .gitignore 忽略，不会进版本库。
rem        zip 不含 .env / configs\sources.yaml / 数据库 / cache / logs / reports / snapshots / backups。
rem ============================================================

set "VER="
for /f "usebackq tokens=* delims= " %%v in ("VERSION") do if not defined VER set "VER=%%v"
if not defined VER (
    echo FAILED: cannot read VERSION file & pause & exit /b 1
)

set "NAME=NetworkIntel-v%VER%-windows-x64-portable"
set "STAGE=dist\%NAME%"
set "ZIP=dist\%NAME%.zip"
set "RELEASE_DIR=E:\Backup\Releases\NetworkIntel"
set "RELEASE_ZIP=%RELEASE_DIR%\%NAME%.zip"

echo ================================================
echo  NetworkIntel - Package Portable
echo  Version: %VER%
echo  Output : %RELEASE_ZIP%
echo ================================================
echo.

echo [1/5] Building GUI exe (PyInstaller, 3-8 min first run) ...
cd python
python -m pip install --upgrade --quiet pyinstaller PySide6 || (
    echo FAILED to install build deps & cd .. & pause & exit /b 1
)
python -m PyInstaller --noconfirm --clean --onefile --windowed --name NetworkIntel ^
  --collect-submodules apscheduler ^
  --collect-submodules tzlocal ^
  --collect-submodules yaml ^
  --collect-all PySide6.QtWebEngineWidgets ^
  --collect-all PySide6.QtWebEngineCore ^
  --hidden-import gui_extensions ^
  --hidden-import gui_map ^
  --hidden-import datasources.setup_profiles ^
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
cd ..

if not exist "python\dist\NetworkIntel.exe" (
    echo BUILD FAILED: python\dist\NetworkIntel.exe not found.
    pause & exit /b 1
)

echo [2/5] Staging portable layout ...
if exist "%STAGE%" rmdir /S /Q "%STAGE%"
mkdir "%STAGE%"
mkdir "%STAGE%\configs"
mkdir "%STAGE%\docs"
copy /Y "python\dist\NetworkIntel.exe" "%STAGE%\NetworkIntel.exe" >nul
copy /Y "configs\sources.example.yaml" "%STAGE%\configs\sources.example.yaml" >nul
copy /Y ".env.example" "%STAGE%\.env.example" >nul
copy /Y "README.md" "%STAGE%\README.md" >nul
copy /Y "docs\RUNNING.txt" "%STAGE%\RUNNING.txt" >nul
copy /Y "docs\RELEASE_NOTES_v%VER%.md" "%STAGE%\docs\RELEASE_NOTES_v%VER%.md" >nul
copy /Y "docs\PORTABLE_MODE.md" "%STAGE%\docs\PORTABLE_MODE.md" >nul
copy /Y "docs\FIRST_RUN_SETUP.md" "%STAGE%\docs\FIRST_RUN_SETUP.md" >nul

echo [3/5] Zipping (top-level folder preserved) ...
if exist "%ZIP%" del /Q "%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path '%STAGE%' -DestinationPath '%ZIP%' -Force"
if not exist "%ZIP%" (
    echo ZIP FAILED.
    pause & exit /b 1
)

echo [4/5] Copying to release dir ...
if not exist "%RELEASE_DIR%" mkdir "%RELEASE_DIR%"
copy /Y "%ZIP%" "%RELEASE_ZIP%" >nul

echo [5/5] Done.
echo.
if exist "%RELEASE_ZIP%" (
    echo DONE: %RELEASE_ZIP%
    for %%I in ("%RELEASE_ZIP%") do echo  Size: %%~zI bytes
) else (
    echo RELEASE COPY FAILED.
)
echo.
pause
