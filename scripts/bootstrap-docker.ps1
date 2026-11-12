# 提权后执行：启用 WSL2 + 静默安装 Docker Desktop
# 由 install-docker.ps1 以管理员身份调用；也可手动用管理员 PowerShell 跑
#
# 注意：提权进程的当前目录是 C:\Windows\System32，所以所有路径必须用绝对路径
param([string]$Installer = "")

$ErrorActionPreference = "Continue"
$log = Join-Path $env:USERPROFILE "docker-install.log"
Start-Transcript -Path $log -Force | Out-Null

function Log($m) { Write-Host ("==> " + $m) -ForegroundColor Cyan }

Log ("开始时间 " + (Get-Date -Format 'HH:mm:ss'))
Log ("身份：" + [Security.Principal.WindowsIdentity]::GetCurrent().Name)
Log ("工作目录：" + (Get-Location).Path)

# ---------- 1. 启用 WSL2 相关 Windows 功能 ----------
Log "启用 Microsoft-Windows-Subsystem-Linux"
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart | Out-Host

Log "启用 VirtualMachinePlatform"
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart | Out-Host

# ---------- 2. 安装 Docker Desktop ----------
if (-not $Installer) {
    $Installer = Join-Path $env:USERPROFILE "Downloads\DockerDesktopInstaller.exe"
}
$Installer = [System.IO.Path]::GetFullPath($Installer)

if (-not (Test-Path $Installer)) {
    Log ("找不到安装包：" + $Installer)
    Stop-Transcript | Out-Null
    exit 2
}
Log ("安装包：" + $Installer + "（" + [math]::Round((Get-Item $Installer).Length / 1MB, 1) + " MB）")

Log "静默安装 Docker Desktop（3-8 分钟，请勿关闭）"
$proc = Start-Process -FilePath $Installer -ArgumentList "install", "--quiet", "--accept-license" -Wait -PassThru
Log ("安装器退出码：" + $proc.ExitCode)

# ---------- 3. 结果 ----------
$docker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
if (Test-Path $docker) {
    Log ("docker.exe 已就位：" + $docker)
    & $docker --version | Out-Host
} else {
    Log "未找到 docker.exe（安装可能未完成）"
}

Log ("结束时间 " + (Get-Date -Format 'HH:mm:ss'))
Stop-Transcript | Out-Null
exit 0
