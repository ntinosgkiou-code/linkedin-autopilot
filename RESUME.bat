@echo off
cd /d "%~dp0"
if exist "%~dp0data\STOP" (type "%~dp0data\STOP" & del "%~dp0data\STOP")
echo.
echo  Autopilot RESUMED.
echo  If it had stopped because of a LinkedIn warning, log in again first:
echo     run 1-INSTALL.bat and answer Y to the LinkedIn login.
pause
