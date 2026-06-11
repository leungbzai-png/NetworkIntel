@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
title NetworkIntel - Package Portable Zip
cd /d "%~dp0"

rem ============================================================
rem  NetworkIntel - 打包 Portable 发布 zip（v0.2.0+）
rem  产物：dist\NetworkIntel-v<VERSION>-portable-win64\ 与同名 .zip
rem  内容：GUI exe + 配置模板(.example) + .env.example + 关键文档
rem  注意：exe / dist / zip 已被 .gitignore 忽略，不会进版本库。
rem ============================================================

set /p VER=<VERSION
echo ================================================
echo  NetworkIntel - Package Portable
echo  Version: %VER%
echo ================================================
echo.

set "STAGE=dist\NetworkIntel-v%VER%-portable-win64"
set "ZIP=dist\NetworkIntel-v%VER%-portable-win64.zip"

echo [1/4] Building GUI exe (PyInstaller, 3-8 min first run) ...
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

echo [2/4] Staging portable layout ...
if exist "%STAGE%" rmdir /S /Q "%STAGE%"
mkdir "%STAGE%"
mkdir "%STAGE%\configs"
copy /Y "python\dist\NetworkIntel.exe" "%STAGE%\NetworkIntel.exe" >nul
copy /Y "configs\sources.example.yaml" "%STAGE%\configs\sources.example.yaml" >nul
copy /Y ".env.example" "%STAGE%\.env.example" >nul
copy /Y "README.md" "%STAGE%\README.md" >nul
if exist "docs\FIRST_RUN_SETUP.md" copy /Y "docs\FIRST_RUN_SETUP.md" "%STAGE%\FIRST_RUN_SETUP.md" >nul
if exist "docs\PORTABLE_MODE.md" copy /Y "docs\PORTABLE_MODE.md" "%STAGE%\PORTABLE_MODE.md" >nul

echo [3/4] Writing quick-start note ...
> "%STAGE%\READ_ME_FIRST.txt" (
    echo NetworkIntel v%VER% - Portable
    echo ============================================================
    echo 1^) 双击 NetworkIntel.exe 启动。首次运行会在本目录自动创建
    echo    configs/ live/ cache/ logs/ reports/ snapshots/ backups/。
    echo 2^) 首次缺少数据库时会弹出「数据初始化」向导：选择
    echo    最小/推荐/完整/自定义，串行下载数据源。
    echo 3^) geoip 需 MaxMind Key：设置页填写后再下载（仅写入 .env）。
    echo 4^) 详见 FIRST_RUN_SETUP.md 与 PORTABLE_MODE.md。
)

echo [4/4] Zipping ...
if exist "%ZIP%" del /Q "%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path '%STAGE%\*' -DestinationPath '%ZIP%' -Force"

echo.
if exist "%ZIP%" (
    echo DONE: %ZIP%
    for %%I in ("%ZIP%") do echo  Size: %%~zI bytes
) else (
    echo ZIP FAILED.
)
echo.
pause
