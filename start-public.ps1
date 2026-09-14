# =============================================================
#  一键启动整套系统并开放公网访问（零成本方案）
#
#  原理：项目用 docker compose 跑在本机，再通过 Cloudflare 免费隧道
#        （cloudflared quick tunnel）把本机端口暴露到公网。
#        无需服务器、无需备案、无需公网 IP。
#
#  用法：在项目根目录执行  .\start-public.ps1
#        停止：直接关掉窗口，或执行  .\start-public.ps1 -Stop
#
#  注意：
#   1. 电脑需要保持开机 + 联网，关闭窗口/关机后公网链接即失效
#   2. 每次启动域名都会变化（quick tunnel 的临时域名）
#   3. 管理端默认不对外暴露（含 admin 账号，暴露到公网有风险）
#      如需暴露，执行 .\start-public.ps1 -ExposeAdmin
# =============================================================

param(
    [switch]$Stop,
    [switch]$ExposeAdmin,
    [int]$UserPort = 8080,
    [int]$AdminPort = 8081
)

# 宽松模式：docker / celery 等工具会把正常进度写到 stderr，
# 若用 Stop 会被误判为错误而中断脚本
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$logDir = Join-Path $env:TEMP 'wt-public'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Find-Cloudflared {
    $candidates = @(
        (Get-Command cloudflared -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        'C:\Program Files (x86)\cloudflared\cloudflared.exe',
        'C:\Program Files\cloudflared\cloudflared.exe'
    ) | Where-Object { $_ -and (Test-Path $_) }
    return $candidates | Select-Object -First 1
}

function Find-Docker {
    $candidates = @(
        (Get-Command docker -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
    ) | Where-Object { $_ -and (Test-Path $_) }
    return $candidates | Select-Object -First 1
}

# ---------- 停止模式 ----------
if ($Stop) {
    Write-Host '>>> 正在停止隧道进程 ...' -ForegroundColor Yellow
    Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force
    Write-Host '>>> 隧道已停止（容器仍在运行，如需停止容器请执行 docker compose down）' -ForegroundColor Green
    exit 0
}

$docker = Find-Docker
$cf = Find-Cloudflared
if (-not $docker) { Write-Host '未找到 docker，请先启动 Docker Desktop' -ForegroundColor Red; exit 1 }
if (-not $cf) { Write-Host '未找到 cloudflared，请先执行: winget install Cloudflare.cloudflared' -ForegroundColor Red; exit 1 }

# ---------- 1. 启动容器 ----------
Write-Host '>>> [1/3] 启动容器 ...' -ForegroundColor Cyan
Push-Location $root
& $docker compose up -d 2>&1 | Out-Null
Pop-Location

Write-Host '>>> [2/3] 等待服务就绪 ...' -ForegroundColor Cyan
$ready = $false
for ($i = 1; $i -le 20; $i++) {
    try {
        # 用真实后端接口探活：前端 nginx 有 SPA 回退，访问 /health 也会返回 200，不能作判据
        $r = Invoke-WebRequest -Uri "http://localhost:$UserPort/api/v1/weather/current" -UseBasicParsing -TimeoutSec 8
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 5
}
if (-not $ready) {
    Write-Host '服务未在预期时间内就绪，请检查 docker compose ps' -ForegroundColor Yellow
}

# ---------- 2. 建立隧道 ----------
Write-Host '>>> [3/3] 建立公网隧道 ...' -ForegroundColor Cyan
$userErr = Join-Path $logDir 'cf-user.err'
Start-Process -FilePath $cf -ArgumentList 'tunnel', '--url', "http://localhost:$UserPort", '--no-autoupdate' `
    -RedirectStandardOutput (Join-Path $logDir 'cf-user.out') -RedirectStandardError $userErr -WindowStyle Hidden

if ($ExposeAdmin) {
    Start-Process -FilePath $cf -ArgumentList 'tunnel', '--url', "http://localhost:$AdminPort", '--no-autoupdate' `
        -RedirectStandardOutput (Join-Path $logDir 'cf-admin.out') -RedirectStandardError (Join-Path $logDir 'cf-admin.err') -WindowStyle Hidden
}

function Get-TunnelUrl($errFile, $timeoutSec = 40) {
    $deadline = (Get-Date).AddSeconds($timeoutSec)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 3
        if (Test-Path $errFile) {
            $m = Select-String -Path $errFile -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' -Encoding UTF8 |
                 Select-Object -First 1
            if ($m) { return $m.Matches[0].Value }
        }
    }
    return $null
}

$userUrl = Get-TunnelUrl $userErr
$adminUrl = if ($ExposeAdmin) { Get-TunnelUrl (Join-Path $logDir 'cf-admin.err') } else { $null }

# ---------- 3. 输出结果 ----------
Write-Host ''
Write-Host '==================== 部署完成 ====================' -ForegroundColor Green
if ($userUrl) {
    Write-Host ("  用户端（可发给别人）:  " + $userUrl) -ForegroundColor Green
} else {
    Write-Host '  用户端隧道地址获取失败，请查看日志: ' -NoNewline -ForegroundColor Yellow; Write-Host $userErr
}
if ($adminUrl) {
    Write-Host ("  管理端（请勿公开）  :  " + $adminUrl) -ForegroundColor Yellow
}
Write-Host ''
Write-Host ("  本机访问  用户端 http://localhost:{0}   管理端 http://localhost:{1}" -f $UserPort, $AdminPort)
Write-Host '  管理员账号 admin / Admin@123456'
Write-Host ''
Write-Host '  停止公网访问:  .\start-public.ps1 -Stop'
Write-Host '  关闭电脑或结束 cloudflared 进程后，公网链接即失效'
Write-Host '=================================================' -ForegroundColor Green
