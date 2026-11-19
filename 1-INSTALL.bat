@echo off
chcp 65001 >nul
title LinkedIn Autopilot - Install
echo.
echo  LinkedIn Autopilot - Step 1: Install
echo  ------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"
echo.
pause
