@echo off
chcp 65001 >nul
title LinkedIn Autopilot - Test
cd /d "%~dp0"
echo.
echo  LinkedIn Autopilot - Step 3: Test run
echo  ------------------------------------
echo  This takes 5-20 minutes. In test mode NOTHING is sent.
echo  Leave this window open.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run.ps1" -Task outreach -Force
echo.
echo  Done. Opening the results...
start "" "%~dp0data"
if exist "%~dp0data\activity_log.csv" start "" "%~dp0data\activity_log.csv"
pause
