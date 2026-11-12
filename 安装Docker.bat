@echo off
title Install Docker Desktop
cd /d "%~dp0"

echo.
echo   Administrator rights needed. Click YES on the UAC dialog.
echo   Installer: %USERPROFILE%\Downloads\DockerDesktopInstaller.exe
echo.
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\install-docker.ps1"
echo.
pause
