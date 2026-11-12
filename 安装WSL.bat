@echo off
title Install WSL2 (required by Docker)
cd /d "%~dp0"

echo.
echo   WSL2 is required by Docker Desktop. Administrator rights needed.
echo   A UAC dialog will appear - click YES.
echo.
net session >nul 2>&1
if %errorlevel%==0 goto elevated

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -ArgumentList '-NoExit','-ExecutionPolicy','Bypass','-File','%~dp0scripts\wsl-setup.ps1' -Verb RunAs"
echo.
echo   Elevation requested.
echo     - UAC shown : click YES, install continues in the new window
echo     - Nothing happened : right-click this file -^> Run as administrator
echo.
pause
exit /b

:elevated
echo   Already elevated - installing now ...
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\wsl-setup.ps1"
pause
