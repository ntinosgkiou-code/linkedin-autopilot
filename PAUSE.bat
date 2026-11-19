@echo off
cd /d "%~dp0"
echo %date% %time% Paused by the user> "%~dp0data\STOP"
echo  Autopilot PAUSED. Nothing will be sent until you run RESUME.bat
pause
