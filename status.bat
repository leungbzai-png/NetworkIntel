@echo off
chcp 65001 >nul
title NetworkIntel - Status
cd /d "%~dp0python"
python do_status.py
pause
