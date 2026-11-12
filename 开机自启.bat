@echo off
cd /d "%~dp0"
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\install-autostart.ps1"
echo.
pause
