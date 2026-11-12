@echo off
title Study-Abroad Agent - Server
cd /d "%~dp0"

echo.
echo   Starting server ...
echo   URL  : http://127.0.0.1:8000/
echo   User : admin / admin123
echo   Close this window to stop.
echo.
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\dev.ps1"
echo.
echo   [ERROR] Server exited. Copy the red text above and send it to me.
pause
