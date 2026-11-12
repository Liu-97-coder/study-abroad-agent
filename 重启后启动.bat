@echo off
title After reboot: WSL + container
cd /d "%~dp0"

echo.
echo   Steps: check WSL -^> start Docker engine -^> build and run container
echo   First run takes about 5-8 minutes.
echo.
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\after-reboot.ps1"
echo.
pause
