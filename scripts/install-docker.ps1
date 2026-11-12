# 安装 Docker Desktop（会自动触发 UAC 提权）+ 检查 WSL2
# 用法：powershell -ExecutionPolicy Bypass -File scripts\install-docker.ps1
#       powershell -ExecutionPolicy Bypass -File scripts\install-docker.ps1 -WslOnly
param(
    [switch]$WslOnly,
    [string]$Installer = ""
)

$ErrorActionPreference = "Continue"
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
} catch { }

function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "    [OK] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "    [!]  $m" -ForegroundColor Yellow }

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

# ---------- 1. WSL2 ----------
if (-not $WslOnly) { Step "1/4 检查 WSL2" } else { Step "检查 WSL2" }
$wslOk = $false
try {
    $status = wsl --status 2>&1 | Out-String
    if ($status -notmatch "not installed|未安装|未找到") { $wslOk = $true }
} catch { $wslOk = $false }

if ($wslOk) {
    Ok "WSL 已就绪"
} else {
    Warn "WSL2 未安装（Docker Desktop 依赖它）"
    if (-not $isAdmin) {
        Write-Host "    需要管理员权限，正在请求提权…" -ForegroundColor Yellow
        $args = @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-WslOnly")
        Start-Process powershell -Verb RunAs -ArgumentList $args
        exit 0
    }
    Write-Host "    执行：wsl --install --no-distribution"
    wsl --install --no-distribution
    Warn "WSL 安装完成，但必须重启电脑才能生效"
    Write-Host @"

  ┌──────────────────────────────────────────────┐
  │  下一步：先重启电脑，再运行 安装Docker.bat     │
  └──────────────────────────────────────────────┘
"@ -ForegroundColor Yellow
    if ($WslOnly) { exit 0 }
}
if ($WslOnly) { exit 0 }

# ---------- 2. 找安装包 ----------
Step "2/4 查找 Docker Desktop 安装包"
$path = if ($Installer) { $Installer } else { Join-Path $env:USERPROFILE "Downloads\DockerDesktopInstaller.exe" }
if (-not (Test-Path $path)) {
    Warn "找不到安装包：$path"
    Write-Host "    下载地址：https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
    Write-Host "    或用 winget：winget install -e --id Docker.DockerDesktop"
    exit 1
}
$size = [math]::Round((Get-Item $path).Length / 1MB, 1)
Ok "$path（$size MB）"

# ---------- 3. 安装（需要提权） ----------
Step "3/4 安装 Docker Desktop"
if (-not $isAdmin) {
    Warn "需要管理员权限，正在请求提权…（会弹 UAC，点"是"）"
    $args = @("-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-Installer", "`"$path`"")
    Start-Process powershell -Verb RunAs -ArgumentList $args
    exit 0
}

Write-Host "    静默安装中（3-8 分钟，别关窗口）…"
$proc = Start-Process -FilePath $path -ArgumentList "install", "--quiet", "--accept-license" -Wait -PassThru
if ($proc.ExitCode -ne 0) {
    Warn "安装器返回 $($proc.ExitCode)。可以手动双击安装包重试"
    exit 1
}
Ok "安装完成"

# ---------- 4. 验证 ----------
Step "4/4 验证"
$docker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
if (Test-Path $docker) {
    $env:Path += ";$(Split-Path $docker)"
    $ver = & $docker --version 2>&1
    Ok "$ver"
}
$desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
if (Test-Path $desktop) { Ok "Docker Desktop 已安装" } else { Warn "未找到 Docker Desktop.exe" }

Write-Host @"

  ┌────────────────────────────────────────────────┐
  │  接下来三步（必须按顺序）                        │
  │                                                │
  │  1. 重启电脑（WSL2 内核要生效）                  │
  │  2. 开始菜单启动 Docker Desktop，等左下角        │
  │     显示 Engine running                         │
  │  3. 回到项目目录双击 启动Docker.bat              │
  └────────────────────────────────────────────────┘
"@ -ForegroundColor Green
