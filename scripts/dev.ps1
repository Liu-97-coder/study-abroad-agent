# 启动开发服务（带热重载）
# 用法（Windows PowerShell 5.1 也可用）：
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 -Port 8010
param(
    [int]$Port = 8000,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $env:PYTHONIOENCODING = "utf-8"
} catch { }
Set-Location (Join-Path $PSScriptRoot "..")

$venvPy = Join-Path (Get-Location) ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "找不到 .venv，请先运行：powershell -ExecutionPolicy Bypass -File scripts\setup.ps1" -ForegroundColor Red
    exit 1
}

$env:PYTHONIOENCODING = "utf-8"

# 端口占用检查：被占用则自动往后找一个空闲端口（最多试 10 个）
function Test-PortFree([int]$p) {
    -not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-PortFree $Port)) {
    $original = $Port
    for ($try = $Port + 1; $try -le $Port + 10; $try++) {
        if (Test-PortFree $try) { $Port = $try; break }
    }
    if ($Port -eq $original) {
        Write-Host "端口 $original ~ $($original + 10) 都被占用了，请重启电脑或手动指定：-Port 9000" -ForegroundColor Red
        exit 1
    }
    Write-Host "端口 $original 被占用，已自动改用 $Port" -ForegroundColor Yellow
}

Write-Host "服务地址： http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "接口文档： http://127.0.0.1:$Port/docs" -ForegroundColor Green
Write-Host "按 Ctrl+C 停止`n" -ForegroundColor DarkGray

$uvArgs = @("-m", "uvicorn", "ai_agent_core.main:app", "--port", "$Port")
if (-not $NoReload) { $uvArgs += "--reload" }
& $venvPy @uvArgs
