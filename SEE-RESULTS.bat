@echo off
cd /d "%~dp0"
if not exist "%~dp0data\reports" mkdir "%~dp0data\reports"
if not exist "%~dp0data\hot_leads.md" echo # People who replied> "%~dp0data\hot_leads.md"
start "" notepad "%~dp0data\hot_leads.md"
start "" "%~dp0data\reports"
