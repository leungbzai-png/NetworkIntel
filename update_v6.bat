@echo off
chcp 65001 >nul
title NetworkIntel - IPv6 Update
cd /d E:\NetworkIntel\python
D:\Python\python.exe do_update_v6.py
pause
