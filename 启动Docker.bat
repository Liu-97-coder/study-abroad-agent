@echo off
title Start Docker container
cd /d "%~dp0"

echo.
echo   Check Docker -^> build image -^> wait for healthy ...
echo.
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\docker-up.ps1"
echo.
pause
