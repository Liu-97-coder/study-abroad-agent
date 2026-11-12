# 开机自启（启动文件夹方案，不需要管理员权限）
# 用法：powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1
#       powershell -ExecutionPolicy Bypass -File scripts\install-autostart.ps1 -Remove
param(
    [switch]$Remove,
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$root = Split-Path $PSScriptRoot -Parent
$vbs = Join-Path $root "启动服务-隐藏.vbs"
$startup = [Environment]::GetFolderPath("Startup")
$link = Join-Path $startup "留学Agent服务.lnk"

if ($Remove) {
    if (Test-Path $link) {
        Remove-Item $link -Force
        Write-Host "已移除开机自启：$link" -ForegroundColor Green
    } else {
        Write-Host "没有找到自启快捷方式" -ForegroundColor Yellow
    }
    exit 0
}

if (-not (Test-Path $vbs)) {
    Write-Host "找不到 启动服务-隐藏.vbs" -ForegroundColor Red
    exit 1
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = "$env:SystemRoot\System32\wscript.exe"
$shortcut.Arguments = "`"$vbs`""
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7
$shortcut.Description = "留学 Agent 服务（隐藏窗口）"
$shortcut.Save()

if (-not $Quiet) {
    Write-Host ""
    Write-Host "已设置开机自启（登录后自动启动，无窗口）" -ForegroundColor Green
    Write-Host "  快捷方式：$link" -ForegroundColor DarkGray
    Write-Host "  日志    ：logs\server.log" -ForegroundColor DarkGray
    Write-Host "  立即试跑：wscript `"$vbs`"" -ForegroundColor DarkGray
    Write-Host "  取消自启：scripts\install-autostart.ps1 -Remove" -ForegroundColor DarkGray
}
exit 0
