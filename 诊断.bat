@echo off
title Environment diagnose
cd /d "%~dp0"

set "OUT=%~dp0runtime\diagnose.txt"
if not exist "%~dp0runtime" mkdir "%~dp0runtime"
echo.
echo   Collecting environment info to runtime\diagnose.txt ...
echo.
(
  echo === diagnose %DATE% %TIME% ===
  echo [user] %USERNAME% @ %COMPUTERNAME%
  echo.
  echo [python]
  python --version 2>&1
  echo.
  echo [venv]
  if exist ".venv\Scripts\python.exe" (echo .venv OK) else (echo .venv MISSING)
  echo.
  echo [port 8000]
  powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalPort,OwningProcess | Format-Table" 2>&1
  echo.
  echo [docker]
  where docker 2>&1
  docker --version 2>&1
  docker info --format "{{.ServerVersion}}" 2>&1
  echo.
  echo [wsl]
  wsl --version 2>&1
  wsl --status 2>&1
  echo.
  echo [hypervisor]
  powershell -NoProfile -Command "(Get-CimInstance Win32_ComputerSystem).HypervisorPresent" 2>&1
  echo.
  echo [installer]
  if exist "%USERPROFILE%\Downloads\DockerDesktopInstaller.exe" (echo downloaded) else (echo missing)
  echo.
  echo [report]
  if exist "logs\docker-report.txt" (type "logs\docker-report.txt") else (echo none)
) > "%OUT%" 2>&1
type "%OUT%"
echo.
echo   Saved to: %OUT%
echo   Send this file to me if something fails.
pause
