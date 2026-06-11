@echo off
chcp 65001 >nul
title NetworkIntel - IPv6 Update
cd /d "%~dp0python"
python do_update_v6.py
pause
