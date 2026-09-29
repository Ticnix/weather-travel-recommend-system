# 脚本已移入 scripts/：自动回到仓库根目录（compose 相对路径依赖它）
Set-Location (Join-Path $PSScriptRoot '..')
# =============================================================
#  用户端「快速改页面」开发服务器
#
#  为什么需要它：改一行文案就要重建镜像 + 重跑测试时，一轮十几分钟。
#  vite dev 是热更新——改完保存、浏览器刷新即可，秒级；而且开发模式
#  不启用 Service Worker，不会出现"改了没生效、其实是缓存"的经典坑。
#
#  用法：在项目根目录执行  .\dev-user.ps1
#        然后打开 http://localhost:5173   （注意不是 8080）
#        停止：Ctrl + C，或直接关掉窗口
#
#  两个地址的分工：
#    5173  开发用：热更新，改完即见（不跑测试、不用重建镜像）
#    8080  正式用：Docker 镜像里构建好的静态包，只在你验收/发布时才重建
#
#  说明：
#   - /api 默认代理到 Docker 后端 8000；本机另起 uvicorn(8001) 时：
#       $env:VITE_API_TARGET = 'http://127.0.0.1:8001'; .\dev-user.ps1
#   - 需要 Node 20+（Vite 8 不支持 Node 18），脚本会自动挑一个
# =============================================================

param(
    [int]$Port = 5173,
    [string]$ApiTarget = 'http://127.0.0.1:8000'
)

$ErrorActionPreference = 'Stop'
$fe = Join-Path $PSScriptRoot 'frontend-user'

# 挑一个 Node 20+：优先 PATH，其次工具自带的多版本目录
$nodeCandidates = @()
$onPath = Get-Command node -ErrorAction SilentlyContinue
if ($onPath) { $nodeCandidates += $onPath.Source }
$versionDir = Join-Path $env:USERPROFILE '.workbuddy\binaries\node\versions'
if (Test-Path $versionDir) {
    $nodeCandidates += Get-ChildItem $versionDir -Directory |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName 'node.exe' } |
        Where-Object { Test-Path $_ }
}

$node = $null
foreach ($candidate in $nodeCandidates) {
    $major = [int](& $candidate -p 'process.versions.node.split(".")[0]')
    if ($major -ge 20) { $node = $candidate; break }
}
if (-not $node) {
    Write-Host '未找到 Node 20+（Vite 8 跑不了 Node 18），请先安装 Node 20 或 22' -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $fe 'node_modules'))) {
    Write-Host '>>> 首次运行，正在安装依赖 ...' -ForegroundColor Yellow
    Push-Location $fe
    & npm install --registry=https://registry.npmmirror.com
    Pop-Location
}

Write-Host ''
Write-Host '==================== 开发服务器 ====================' -ForegroundColor Green
Write-Host "  Node      : $node"
Write-Host "  API 代理  : $ApiTarget"
Write-Host "  打开地址  : http://localhost:$Port" -ForegroundColor Green
Write-Host '  改完代码保存即生效；不需要重建镜像，也不会被 SW 缓存挡住' -ForegroundColor Cyan
Write-Host '====================================================='
Write-Host ''

Push-Location $fe
$env:VITE_API_TARGET = $ApiTarget
try {
    & $node 'node_modules/vite/bin/vite.js' --port $Port
} finally {
    Pop-Location
}
