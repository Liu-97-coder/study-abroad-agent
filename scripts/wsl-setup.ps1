# 提权执行：安装 WSL 内核（重启后功能已生效，这一步才会真的装上）
$ErrorActionPreference = "Continue"
$out = Join-Path $env:USERPROFILE "wsl-setup.log"
Start-Transcript -Path $out -Force | Out-Null

function Log($m) { Write-Host ("==> " + $m) -ForegroundColor Cyan }

Log ("开始 " + (Get-Date -Format 'HH:mm:ss'))
Log ("身份：" + [Security.Principal.WindowsIdentity]::GetCurrent().Name)

Log "wsl --version（安装前）"
wsl --version 2>&1 | Out-Host

Log "执行 wsl --install --no-distribution"
wsl --install --no-distribution 2>&1 | Out-Host

Log "设置默认版本 2"
wsl --set-default-version 2 2>&1 | Out-Host

Log "wsl --update"
wsl --update 2>&1 | Out-Host

Log "wsl --version（安装后）"
wsl --version 2>&1 | Out-Host
Log ("退出码：" + $LASTEXITCODE)

Log ("结束 " + (Get-Date -Format 'HH:mm:ss'))
Stop-Transcript | Out-Null

# 装完直接串起后续：启引擎 → 构建镜像 → 等 healthy
$next = Join-Path (Split-Path $PSScriptRoot -Parent) "scripts\after-reboot.ps1"
if ((Test-Path $next) -and ($LASTEXITCODE -eq 0)) {
    Write-Host "`n==> WSL 就绪，继续启动 Docker 容器…" -ForegroundColor Green
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$next`""
} else {
    Write-Host "`n[!] WSL 安装未成功返回。请再运行一次本脚本，或重启后运行 重启后启动.bat" -ForegroundColor Yellow
    Read-Host "按回车关闭"
}
