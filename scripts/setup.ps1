# 一键环境准备（Windows / PowerShell 5.1 及以上）
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Mirror https://pypi.tuna.tsinghua.edu.cn/simple
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Force      # 重建虚拟环境
param(
    [switch]$Force,
    [switch]$SkipSmoke,
    [string]$Mirror = ""
)

$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $env:PYTHONIOENCODING = "utf-8"
} catch { }
Set-Location (Join-Path $PSScriptRoot "..")
$root = Get-Location

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    [!]  $msg" -ForegroundColor Yellow }

Write-Host "项目目录：$root" -ForegroundColor DarkGray

# ---------- 1. 检查 Python ----------
Step "1/6 检查 Python"
$pythonCmd = $null
foreach ($candidate in @("python", "py")) {
    try {
        $ver = & $candidate --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $pythonCmd = $candidate
                Ok "$candidate → $ver"
                break
            } else {
                Warn "$candidate 版本过低（$ver），需要 3.10+"
            }
        }
    } catch { }
}
if (-not $pythonCmd) {
    Write-Host "`n找不到 Python 3.10+。请先安装：" -ForegroundColor Red
    Write-Host "  https://www.python.org/downloads/windows/  （安装时勾选 Add python.exe to PATH）"
    exit 1
}

# ---------- 2. 创建虚拟环境 ----------
Step "2/6 准备虚拟环境 .venv"
if ($Force -and (Test-Path ".venv")) {
    Remove-Item -Recurse -Force ".venv"
    Warn "已删除旧的 .venv"
}
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $pythonCmd -m venv .venv
    Ok "已创建 .venv"
} else {
    Ok ".venv 已存在，跳过创建"
}
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

# ---------- 3. 安装依赖 ----------
Step "3/6 安装依赖（首次约 1-3 分钟）"
& $venvPy -m pip install --quiet --upgrade pip
$pipArgs = @("-m", "pip", "install", "--quiet", "-r", "requirements.txt")
if ($Mirror -ne "") { $pipArgs += @("-i", $Mirror) }
& $venvPy @pipArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n依赖安装失败。常见原因：网络慢或代理问题。" -ForegroundColor Red
    Write-Host "重试一次并指定国内镜像："
    Write-Host "  pwsh -File scripts\setup.ps1 -Mirror https://pypi.tuna.tsinghua.edu.cn/simple"
    exit 1
}
& $venvPy -c "import fastapi, pydantic, langgraph; print('    [OK] fastapi/pydantic/langgraph 就绪')"

# ---------- 4. 配置文件 ----------
Step "4/6 生成 .env"
if (Test-Path ".env") {
    Ok ".env 已存在，保留你的配置"
} else {
    Copy-Item ".env.example" ".env"
    Ok "已从 .env.example 生成 .env（默认 mock 模式，不花钱）"
}

# ---------- 5. 灌知识库 ----------
Step "5/6 导入知识库种子数据"
& $venvPy "scripts\ingest_seed.py"
if ($LASTEXITCODE -ne 0) {
    Write-Host "知识库导入失败，先解决上面的报错再继续。" -ForegroundColor Red
    exit 1
}

# ---------- 6. 自测 ----------
if ($SkipSmoke) {
    Step "6/6 跳过自测（-SkipSmoke）"
} else {
    Step "6/6 端到端自测"
    & $venvPy "scripts\smoke_test.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n自测未全绿，看上面的【断言】哪一条 FAIL。" -ForegroundColor Yellow
        exit $LASTEXITCODE
    }
}

Write-Host "`n============================================" -ForegroundColor Green
Write-Host " 环境就绪！下一步：" -ForegroundColor Green
Write-Host "   powershell -ExecutionPolicy Bypass -File scripts\dev.ps1" -ForegroundColor Green
Write-Host "   浏览器打开 http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
