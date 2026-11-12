# 一键起 Docker（检查环境 → 启动 → 等健康 → 打印地址）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\docker-up.ps1
#       powershell -ExecutionPolicy Bypass -File scripts\docker-up.ps1 -Port 8010
param(
    [int]$Port = 8000,
    [switch]$Rebuild
)

$ErrorActionPreference = "Continue"
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
} catch { }
Set-Location (Join-Path $PSScriptRoot "..")

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    [OK] $msg" -ForegroundColor Green }
function Warn($msg) { Write-Host "    [!]  $msg" -ForegroundColor Yellow }

# ---------- 1. Docker 是否可用 ----------
Step "1/5 检查 Docker"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Warn "没有找到 docker 命令"
    Write-Host @"

这台机器还没装 Docker。两条路：

  A. 装 Docker Desktop（推荐，Windows 10/11）
     1) 下载 https://www.docker.com/products/docker-desktop/
     2) 安装时勾选 "Use WSL 2 instead of Hyper-V"
     3) 如果提示缺 WSL：管理员 PowerShell 执行  wsl --install   然后重启电脑
     4) 启动 Docker Desktop，等左下角显示 Engine running
     5) 回来重跑本脚本

  B. 不装 Docker：直接本机跑
     powershell -ExecutionPolicy Bypass -File scripts\dev.ps1

想先确认"镜像依赖是否完整"，可跑等价验证：
     .\.venv\Scripts\python.exe scripts\check_deploy.py
"@ -ForegroundColor Yellow
    exit 1
}
Ok ((docker version --format '{{.Server.Version}}' 2>$null) -join "")

# ---------- 2. Docker 引擎是否在跑 ----------
Step "2/5 检查 Docker 引擎"
$engine = docker info --format '{{.ServerVersion}}' 2>&1
if ($LASTEXITCODE -ne 0) {
    Warn "Docker 引擎没启动，尝试拉起 Docker Desktop…"
    $desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $desktop) {
        Start-Process $desktop
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 3
            docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) { Ok "引擎已就绪"; break }
        }
    } else {
        Warn "找不到 Docker Desktop.exe，请手动启动后重试"
        exit 1
    }
} else {
    Ok "引擎已就绪（$engine）"
}

# ---------- 3. .env ----------
Step "3/5 准备 .env"
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Ok "已生成 .env（生产请改 AUTH_SECRET）"
} else {
    Ok ".env 已存在"
}
$secret = (Select-String -Path ".env" -Pattern '^AUTH_SECRET=(.*)$').Matches.Groups[1].Value
if ($secret -like "dev-secret*") {
    Warn "AUTH_SECRET 还是默认值，生产环境必须改成随机值"
}

# ---------- 4. 构建并启动 ----------
Step "4/5 构建并启动容器"
$env:APP_PORT = "$Port"
if ($Rebuild) {
    docker compose up -d --build
} else {
    docker compose up -d --build
}
if ($LASTEXITCODE -ne 0) {
    Warn "启动失败，看日志：docker compose logs agent"
    exit 1
}

# ---------- 5. 等健康检查 ----------
Step "5/5 等待健康检查"
$healthy = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 3
    $state = docker inspect --format '{{.State.Health.Status}}' study-abroad-agent 2>$null
    if ($state -eq "healthy") { $healthy = $true; break }
    Write-Host "    当前状态：$state" -ForegroundColor DarkGray
}

if (-not $healthy) {
    Warn "40 次轮询仍未 healthy，打印最近日志："
    docker compose logs --tail 40 agent
    exit 1
}

Write-Host "`n============================================" -ForegroundColor Green
Write-Host " 服务已就绪" -ForegroundColor Green
Write-Host "   控制台：http://127.0.0.1:$Port/" -ForegroundColor Green
Write-Host "   接口：  http://127.0.0.1:$Port/docs" -ForegroundColor Green
Write-Host "   账号：  admin / admin123" -ForegroundColor Green
Write-Host "   日志：  docker compose logs -f agent" -ForegroundColor DarkGray
Write-Host "   停止：  docker compose down" -ForegroundColor DarkGray
Write-Host "============================================" -ForegroundColor Green
