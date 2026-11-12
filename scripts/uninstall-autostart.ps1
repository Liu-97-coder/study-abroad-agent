# 取消开机自启并停止服务
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

$taskName = "StudyAbroadAgent"
schtasks /Query /TN $taskName *> $null
if ($LASTEXITCODE -eq 0) {
    schtasks /End /TN $taskName *> $null
    schtasks /Delete /TN $taskName /F *> $null
    Write-Host "已删除计划任务 $taskName" -ForegroundColor Green
} else {
    Write-Host "没有找到计划任务 $taskName" -ForegroundColor Yellow
}

# 顺手把占用 8000 的 python 服务停掉
$conns = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
foreach ($c in $conns) {
    $p = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
    if ($p -and $p.ProcessName -like "python*") {
        Write-Host ("停止进程 " + $p.Id) -ForegroundColor Yellow
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
}
exit 0
