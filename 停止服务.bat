@echo off
title Study-Abroad Agent - Stop
cd /d "%~dp0"

powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1"
echo.
pause
