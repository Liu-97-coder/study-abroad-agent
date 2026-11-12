# 停止本项目的所有服务实例（按端口精确清理，含 uvicorn reload 的子进程）
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\stop.ps1 -From 8000 -To 8010
param(
    [int]$From = 8000,
    [int]$To = 8010,
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
} catch { }

$found = @()
for ($port = $From; $port -le $To; $port++) {
    $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        if ($c.OwningProcess -and ($found -notcontains $c.OwningProcess)) {
            $found += $c.OwningProcess
            if (-not $Quiet) { Write-Host "端口 $port → 结束进程 $($c.OwningProcess)" -ForegroundColor Yellow }
            # /T 连带子进程，uvicorn --reload 的 worker 才会一起退出
            & taskkill /F /T /PID $c.OwningProcess | Out-Null
        }
    }
}

# 再兜一层：按命令行匹配本项目的 uvicorn 进程
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*uvicorn ai_agent_core*' } |
    ForEach-Object {
        if (-not $Quiet) { Write-Host "命令行匹配 → 结束进程 $($_.ProcessId)" -ForegroundColor Yellow }
        & taskkill /F /T /PID $_.ProcessId | Out-Null
    }

Start-Sleep -Milliseconds 800

$left = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalPort -ge $From -and $_.LocalPort -le $To }
if ($left) {
    Write-Host "`n仍有端口被占用（可能是管理员权限启动的进程）：" -ForegroundColor Red
    $left | Select-Object LocalPort, OwningProcess | Format-Table -AutoSize | Out-String | Write-Host
    Write-Host "处理办法：以管理员身份运行本脚本，或直接重启电脑。" -ForegroundColor Yellow
    exit 1
}

if (-not $Quiet) { Write-Host "`n已全部停止，端口 $From-$To 空闲。" -ForegroundColor Green }
exit 0
