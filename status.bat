@echo off
chcp 65001 >nul
title NetworkIntel - Status
cd /d E:\NetworkIntel\python
D:\Python\python.exe do_status.py
pause
