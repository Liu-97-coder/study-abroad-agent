# 重置本地数据（知识库索引 / 客户中台 / 日志 / 缓存）
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\reset.ps1          # 交互确认
#   powershell -ExecutionPolicy Bypass -File scripts\reset.ps1 -Yes     # 不确认直接删
#   powershell -ExecutionPolicy Bypass -File scripts\reset.ps1 -KeepRag # 只清客户数据与日志，保留知识库
param(
    [switch]$Yes,
    [switch]$KeepRag
)

$ErrorActionPreference = "Stop"
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $env:PYTHONIOENCODING = "utf-8"
} catch { }
Set-Location (Join-Path $PSScriptRoot "..")

$targets = @("runtime\crm.db")
if (-not $KeepRag) { $targets += "runtime\rag" }
$targets += "logs"

Write-Host "将要删除：" -ForegroundColor Yellow
foreach ($t in $targets) {
    if (Test-Path $t) { Write-Host "  - $t" }
}

if (-not $Yes) {
    $answer = Read-Host "确认删除？(y/N)"
    if ($answer -ne "y" -and $answer -ne "Y") {
        Write-Host "已取消。" -ForegroundColor DarkGray
        exit 0
    }
}

foreach ($t in $targets) {
    if (Test-Path $t) {
        Remove-Item -Recurse -Force $t
        Write-Host "  已删除 $t" -ForegroundColor Green
    }
}

New-Item -ItemType Directory -Force -Path "logs", "runtime\rag" | Out-Null
Write-Host "`n完成。重新灌库：powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SkipSmoke" -ForegroundColor Green
