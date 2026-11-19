@echo off
chcp 65001 >nul
title LinkedIn Autopilot
cd /d "%~dp0"
set "PATH=%USERPROFILE%\.local\bin;%APPDATA%\npm;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Needs a small helper tool called "uv" ^(about 20 MB, from astral.sh^).
  choice /m "  Install it now"
  if errorlevel 2 exit /b
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)
where uv >nul 2>nul
if errorlevel 1 (
  echo  uv did not install. Close this window and run START.bat again.
  pause
  exit /b 1
)
:run
echo.
echo  Opening LinkedIn Autopilot in your browser...
echo  Keep this window open while you use the dashboard.
call uv run --quiet "%~dp0ui\server.py"
if errorlevel 1 (
  echo.
  echo  The dashboard stopped unexpectedly. Restarting in 3 seconds... ^(details: data\ui.log^)
  ping -n 4 127.0.0.1 >nul
  goto run
)
echo.
echo  Dashboard closed. The automatic daily work keeps running without it.
pause
