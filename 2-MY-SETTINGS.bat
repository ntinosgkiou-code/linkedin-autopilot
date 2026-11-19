@echo off
chcp 65001 >nul
title LinkedIn Autopilot - My settings
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%APPDATA%\npm;%PATH%"
echo.
echo  LinkedIn Autopilot - Step 2: Your settings
echo  ------------------------------------------
echo  Claude will open and ask you a few questions.
echo  When you are finished, type  /exit  and press Enter.
echo.
pause
call claude "setup"
echo.
echo  Saving your schedule...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1" -ScheduleOnly
pause
