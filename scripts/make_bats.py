"""生成 Windows 批处理：纯 ASCII + CRLF。

教训：
- .bat 里写中文，无论 GBK 还是 UTF-8 都会在某种控制台上乱码（代码页 936 / 65001 打架）
- 批处理只做"启动器"：纯 ASCII，中文提示全部交给 PowerShell 脚本输出
  （PowerShell 通过 Unicode 控制台 API 输出，不受 chcp 影响）
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HEADER = """@echo off
title {title}
cd /d "%~dp0"
"""

FILES = {
    "启动服务.bat": HEADER.format(title="Study-Abroad Agent - Server") + """
echo.
echo   Starting server ...
echo   URL  : http://127.0.0.1:8000/
echo   User : admin / admin123
echo   Close this window to stop.
echo.
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\\dev.ps1"
echo.
echo   [ERROR] Server exited. Copy the red text above and send it to me.
pause
""",

    "停止服务.bat": HEADER.format(title="Study-Abroad Agent - Stop") + """
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\\stop.ps1"
echo.
pause
""",

    "安装WSL.bat": HEADER.format(title="Install WSL2 (required by Docker)") + """
echo.
echo   WSL2 is required by Docker Desktop. Administrator rights needed.
echo   A UAC dialog will appear - click YES.
echo.
net session >nul 2>&1
if %errorlevel%==0 goto elevated

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -ArgumentList '-NoExit','-ExecutionPolicy','Bypass','-File','%~dp0scripts\\wsl-setup.ps1' -Verb RunAs"
echo.
echo   Elevation requested.
echo     - UAC shown : click YES, install continues in the new window
echo     - Nothing happened : right-click this file -^> Run as administrator
echo.
pause
exit /b

:elevated
echo   Already elevated - installing now ...
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\\wsl-setup.ps1"
pause
""",

    "安装Docker.bat": HEADER.format(title="Install Docker Desktop") + """
echo.
echo   Administrator rights needed. Click YES on the UAC dialog.
echo   Installer: %USERPROFILE%\\Downloads\\DockerDesktopInstaller.exe
echo.
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\\install-docker.ps1"
echo.
pause
""",

    "启动Docker.bat": HEADER.format(title="Start Docker container") + """
echo.
echo   Check Docker -^> build image -^> wait for healthy ...
echo.
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\\docker-up.ps1"
echo.
pause
""",

    "重启后启动.bat": HEADER.format(title="After reboot: WSL + container") + """
echo.
echo   Steps: check WSL -^> start Docker engine -^> build and run container
echo   First run takes about 5-8 minutes.
echo.
powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0scripts\\after-reboot.ps1"
echo.
pause
""",

    "打开项目.bat": HEADER.format(title="Open project") + """
set "PROJ=%~dp0"
if "%PROJ:~-1%"=="\\" set "PROJ=%PROJ:~0,-1%"
echo ==================================================
echo   %PROJ%
echo ==================================================
echo.
echo %PROJ%| clip
echo [+] Path copied to clipboard.

set "VSCODE=%LOCALAPPDATA%\\Programs\\Microsoft VS Code\\Code.exe"
if not exist "%VSCODE%" set "VSCODE=%ProgramFiles%\\Microsoft VS Code\\Code.exe"

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
""",

    "诊断.bat": HEADER.format(title="Environment diagnose") + """
set "OUT=%~dp0runtime\\diagnose.txt"
if not exist "%~dp0runtime" mkdir "%~dp0runtime"
echo.
echo   Collecting environment info to runtime\\diagnose.txt ...
echo.
(
  echo === diagnose %DATE% %TIME% ===
  echo [user] %USERNAME% @ %COMPUTERNAME%
  echo.
  echo [python]
  python --version 2>&1
  echo.
  echo [venv]
  if exist ".venv\\Scripts\\python.exe" (echo .venv OK) else (echo .venv MISSING)
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
  if exist "%USERPROFILE%\\Downloads\\DockerDesktopInstaller.exe" (echo downloaded) else (echo missing)
  echo.
  echo [report]
  if exist "logs\\docker-report.txt" (type "logs\\docker-report.txt") else (echo none)
) > "%OUT%" 2>&1
type "%OUT%"
echo.
echo   Saved to: %OUT%
echo   Send this file to me if something fails.
pause
""",
}


def main() -> int:
    for name, content in FILES.items():
        text = content.replace("\r\n", "\n").replace("\n", "\r\n")
        data = text.encode("ascii", errors="replace")   # 纯 ASCII，杜绝乱码
        (ROOT / name).write_bytes(data)
        non_ascii = sum(1 for b in data if b > 127)
        print(f"写入 {name}（{len(data)} 字节，非 ASCII 字节 {non_ascii}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
