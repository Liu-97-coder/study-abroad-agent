# 重启后一键把 Docker 环境补齐并启动项目（双击 重启后启动.bat 即可）
# 做的事：等 WSL2 就绪 → 拉起 Docker 引擎 → 构建镜像 → 等 healthy → 写报告
param([int]$Port = 8000)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$report = Join-Path $root "logs\docker-report.txt"
New-Item -ItemType Directory -Force -Path (Split-Path $report) | Out-Null

function Step($m) { Write-Host ("`n==> " + $m) -ForegroundColor Cyan }
function Ok($m)   { Write-Host ("    [OK] " + $m) -ForegroundColor Green }
function Warn($m) { Write-Host ("    [!]  " + $m) -ForegroundColor Yellow }
function Rec($m)  { Add-Content -Path $report -Value $m -Encoding UTF8 }

"" | Set-Content $report -Encoding UTF8
Rec ("=== 环境报告 " + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + " ===")

$dockerBin = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin"
if (Test-Path $dockerBin) { $env:Path += ";$dockerBin" }

# ---------- 1. 环境探测 ----------
Step "1/5 探测 WSL 是否已生效"
$wslProbe = wsl --version 2>&1 | Out-String
$wslOk = ($LASTEXITCODE -eq 0 -and $wslProbe -notmatch "not installed|未安装")
Rec ("wsl --version 退出码：" + $LASTEXITCODE)
if ($wslOk) {
    Ok (($wslProbe -split "`n")[0].Trim())
} else {
    Warn "WSL 还没生效 —— 如果刚刚启用功能，请再重启一次；否则我尝试安装内核"
    Rec "WSL: 未生效"
}

# ---------- 2. WSL2 ----------
Step "2/5 初始化 WSL2"
if (-not $wslOk) {
    Warn "尝试安装 WSL 内核（会弹 UAC，最多等 3 分钟）"
    $job = Start-Process powershell -Verb RunAs -PassThru -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
        "wsl --install --no-distribution; wsl --set-default-version 2"
    )
    $job | Wait-Process -Timeout 180 -ErrorAction SilentlyContinue
    if (-not $job.HasExited) { $job | Stop-Process -Force -ErrorAction SilentlyContinue }
    $wslProbe = wsl --version 2>&1 | Out-String
    $wslOk = ($LASTEXITCODE -eq 0)
}
if ($wslOk) { Ok "WSL 就绪"; Rec ("WSL: " + $wslProbe.Trim()) }
else { Warn "WSL 仍未就绪；请再重启一次后重跑本脚本"; Rec "WSL: 未就绪" }

# ---------- 3. Docker 引擎 ----------
Step "3/5 启动 Docker 引擎"
$desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
$engineReady = $false
for ($i = 0; $i -lt 40; $i++) {
    docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $engineReady = $true; break }
    if ($i -eq 0 -and (Test-Path $desktop)) { Start-Process $desktop; Ok "已启动 Docker Desktop" }
    Start-Sleep -Seconds 6
}
if (-not $engineReady) {
    Warn "引擎 4 分钟内没起来。打开 Docker Desktop 看提示（常见：WSL 还需要重启一次）"
    Rec "引擎：未就绪"
    exit 1
}
Ok ((docker info --format 'Server {{.ServerVersion}}') + " · " +
    (docker info --format '{{.OperatingSystem}}'))
Rec ("引擎：" + (docker info --format 'Server {{.ServerVersion}}'))

# ---------- 4. 构建并启动 ----------
Step "4/5 构建镜像并启动（首次 3-6 分钟）"
$env:APP_PORT = "$Port"
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Warn "compose 失败，最近日志："
    docker compose logs --tail 40 agent
    Rec "结果：compose 失败"
    exit 1
}

# ---------- 5. 等健康检查 ----------
Step "5/5 等待健康检查"
$healthy = $false
for ($i = 0; $i -lt 50; $i++) {
    Start-Sleep -Seconds 4
    $state = docker inspect --format '{{.State.Health.Status}}' study-abroad-agent 2>$null
    if ($state -eq "healthy") { $healthy = $true; break }
    if ($i % 5 -eq 0) { Write-Host ("    状态：" + $state) -ForegroundColor DarkGray }
}
if (-not $healthy) {
    Warn "未达到 healthy，打印日志："
    docker compose logs --tail 50 agent
    Rec "结果：不健康"
    docker compose ps | Out-Host
    exit 1
}

Ok "容器 healthy"
docker compose ps | Out-Host
Rec "结果：healthy"
Rec ("镜像：" + (docker inspect --format '{{.Config.Image}}' study-abroad-agent))
Rec ("端口：" + $Port)

Write-Host @"

  ============================================
   容器已就绪
     控制台：http://127.0.0.1:$Port/
     账号：  admin / admin123
     日志：  docker compose logs -f agent
     报告：  logs\docker-report.txt
  ============================================
"@ -ForegroundColor Green
