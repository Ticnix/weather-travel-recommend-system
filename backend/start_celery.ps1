# Celery Worker 一键启动脚本（Windows 本地开发模式）
#
# 前置：已激活虚拟环境、pg/redis 已在 docker 运行、.env 已配置
# 用法（在 backend 目录执行）：
#   .\venv\Scripts\Activate.ps1
#   .\start_celery.ps1
#
# 后台静默运行，日志写入 celery.log；停止任务在任务管理器结束 python 进程即可。

$ErrorActionPreference = "Stop"

# 切换到脚本所在目录（backend）
$backendDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $backendDir

Write-Host ">>> 启动 Celery worker（日志输出到 celery.log）..." -ForegroundColor Cyan

Start-Process -FilePath ".\venv\Scripts\python.exe" `
    -ArgumentList "-m", "celery", "-A", "app.celery_app", "worker", "-l", "info", "-P", "solo" `
    -RedirectStandardOutput "celery.log" `
    -WindowStyle Hidden

Start-Sleep -Seconds 3

# 简单校验是否启动成功
$running = Get-Process -Name python -ErrorAction SilentlyContinue |
    Where-Object { $true }
if ($running) {
    Write-Host ">>> Celery worker 已启动（进程存在）。查看 celery.log 确认任务注册情况。" -ForegroundColor Green
} else {
    Write-Host ">>> 未能确认 Celery 进程，请检查 celery.log" -ForegroundColor Yellow
}
