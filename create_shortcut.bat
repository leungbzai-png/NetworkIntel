@echo off
chcp 65001 >nul

set "SHORTCUT=%USERPROFILE%\Desktop\NetworkIntel.lnk"
set "TARGET=E:\NetworkIntel\start.bat"
set "ICON=%SystemRoot%\System32\shell32.dll,13"
set "WORKDIR=E:\NetworkIntel"

powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath='%TARGET%';" ^
  "$s.WorkingDirectory='%WORKDIR%';" ^
  "$s.IconLocation='%ICON%';" ^
  "$s.WindowStyle=1;" ^
  "$s.Description='NetworkIntel - IP Intelligence Platform';" ^
  "$s.Save()"

if exist "%SHORTCUT%" (
    echo Done! Shortcut created on desktop.
) else (
    echo Failed.
)
pause
