@echo off
title Open project
cd /d "%~dp0"

set "PROJ=%~dp0"
if "%PROJ:~-1%"=="\" set "PROJ=%PROJ:~0,-1%"
echo ==================================================
echo   %PROJ%
echo ==================================================
echo.
echo %PROJ%| clip
echo [+] Path copied to clipboard.

set "VSCODE=%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"
if not exist "%VSCODE%" set "VSCODE=%ProgramFiles%\Microsoft VS Code\Code.exe"

if exist "%VSCODE%" (
    echo [+] Opening VS Code ...
    start "" "%VSCODE%" "%PROJ%"
) else (
    echo [!] VS Code not found. Open the folder manually:
    echo     %PROJ%
)

echo [+] Opening File Explorer ...
start "" explorer "%PROJ%"
echo.
echo   Next: double-click the server launcher.
echo.
pause
