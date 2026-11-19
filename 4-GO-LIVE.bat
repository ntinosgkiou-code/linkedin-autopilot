@echo off
chcp 65001 >nul
title LinkedIn Autopilot - Go live
cd /d "%~dp0"
echo.
echo  From now on the autopilot SENDS real invites and messages from your LinkedIn.
echo  Close this window if you are not sure.
echo.
pause
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%~dp0config.yaml'; $t=[IO.File]::ReadAllText($p); $t=$t -replace 'mode:\s*\"dry_run\"','mode: \"live\"'; [IO.File]::WriteAllText($p,$t,(New-Object Text.UTF8Encoding $false)); if($t -match 'mode: \"live\"'){'LIVE: the autopilot is on.'}else{'Could not find the mode line in config.yaml'}"
pause
