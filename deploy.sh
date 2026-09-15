#!/usr/bin/env bash
# ============================================================================
# deploy.sh —— 一条命令完成上线：
#   备份数据库 → 停应用 → 拉取镜像 → 启动 → 健康检查 → 失败自动回滚
#
# 用法：
#   ./deploy.sh                             # 部署主干最新版（latest）
#   IMAGE_TAG=sha-4c3abe9 ./deploy.sh       # 部署指定版本
#   IMAGE_TAG=sha-1234567 ./deploy.sh       # 同一条命令就是回滚：换个旧 tag 再跑
#
# 可调环境变量：
#   IMAGE_TAG               要部署的镜像标签（默认 latest）
#   KEEP_BACKUPS            备份保留份数（默认 7）
#   HEALTHCHECK_TIMEOUT_S   健康检查总时限（默认 90 秒）
#   FORCE_HEALTHCHECK_FAIL  设为 1 时健康检查必定失败（仅用于演练回滚流程）
#
# 退出码：
#   0  部署成功
#   1  部署失败（已自动回滚到上一版本）
#   2  部署失败且回滚也失败 —— 需要人工介入，此时数据库已有部署前备份
#
# 设计说明：
#   - 备份放在「停应用之后、换镜像之前」：应用停止后数据不再变化，
#     pg_dump 拿到的是一致性快照；停机窗口本来就等于部署窗口，不额外损失
#   - 回滚不重新 pull：旧版本的镜像在本地一定存在（刚才就是它跑着的），
#     所以回滚不需要网络，秒级完成
#   - 数据库/Redis 容器全程不重启，业务数据卷不受影响
#
# Windows 注意：请在 Git Bash 中运行（安装 Git 后自带），不要用 PowerShell。
# ============================================================================
set -uo pipefail

IMAGE_TAG="${IMAGE_TAG:-latest}"
KEEP_BACKUPS="${KEEP_BACKUPS:-7}"
HEALTHCHECK_TIMEOUT_S="${HEALTHCHECK_TIMEOUT_S:-90}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$PROJECT_ROOT/backups"
COMPOSE="docker compose"

log()  { printf '[deploy] %s\n' "$*"; }
fail() { printf '[deploy][错误] %s\n' "$*" >&2; exit 1; }

cd "$PROJECT_ROOT" || fail "无法进入项目根目录：$PROJECT_ROOT"

# ---------- 0. 预检查：缺什么提前说，别跑到一半才失败 ----------
command -v docker >/dev/null 2>&1 || fail "未找到 docker，请先安装并启动 Docker"
[ -f docker-compose.yml ]    || fail "找不到 docker-compose.yml"
$COMPOSE version >/dev/null 2>&1 || fail "docker compose 不可用（需要 Compose V2）"

log "目标版本: $IMAGE_TAG"

# ---------- 1. 记录当前版本（回滚的依据） ----------
OLD_TAG="未知"
[ -f .last_deployed_tag ] && OLD_TAG="$(cat .last_deployed_tag)"
log "当前运行版本: $OLD_TAG"

# ---------- 2. 停应用容器（数据库保持运行） ----------
# 只停会写数据/对外服务的容器；postgres、redis 不动
log "停止应用容器（数据库保持运行）..."
$COMPOSE stop backend celery frontend-user frontend-admin >/dev/null 2>&1 || true

# ---------- 3. 备份数据库（应用已停，数据一致） ----------
mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_FILE="$BACKUP_DIR/weather_db-$STAMP.sql.gz"
log "备份数据库 → $BACKUP_FILE"
$COMPOSE exec -T postgres pg_dump -U admin -d weather_db | gzip > "$BACKUP_FILE" \
  || fail "数据库备份失败，已中止部署（数据未受影响，旧容器已停止）"

# 校验备份真的可用：非空 + gzip 完整性。防止「备份了个寂寞」后继续往下走
[ -s "$BACKUP_FILE" ] || fail "备份文件为空，中止部署"
gzip -t "$BACKUP_FILE" || fail "备份文件损坏（gzip 校验未通过），中止部署"
log "备份完成: $(du -h "$BACKUP_FILE" | cut -f1)"

# 只保留最近 KEEP_BACKUPS 份，防止备份目录悄悄吃满磁盘
ls -1t "$BACKUP_DIR"/weather_db-*.sql.gz 2>/dev/null \
  | tail -n +$((KEEP_BACKUPS + 1)) \
  | while IFS= read -r old; do
      rm -f "$old"
      log "清理过期备份: $(basename "$old")"
    done

# ---------- 4. 拉取新镜像（此时服务本来就是停的，失败无副作用） ----------
log "拉取镜像（IMAGE_TAG=$IMAGE_TAG）..."
IMAGE_TAG="$IMAGE_TAG" $COMPOSE pull backend celery frontend-user frontend-admin \
  || fail "镜像拉取失败：请确认 GHCR 上是否存在该 tag。数据已备份在 $BACKUP_FILE"

# ---------- 5. 启动新版本 ----------
log "启动服务..."
IMAGE_TAG="$IMAGE_TAG" $COMPOSE up -d || fail "容器启动失败（数据已备份于 $BACKUP_FILE）"

# ---------- 6. 健康检查：三个入口全部可用才算上线成功 ----------
check_health() {
  local deadline=$(( $(date +%s) + HEALTHCHECK_TIMEOUT_S ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    # FORCE_HEALTHCHECK_FAIL=1：演练回滚流程用，跳过真实探测
    if [ "${FORCE_HEALTHCHECK_FAIL:-0}" != "1" ] \
       && curl -fsS --max-time 5 http://localhost:8000/health >/dev/null 2>&1 \
       && curl -fsS --max-time 5 http://localhost:8080/      >/dev/null 2>&1 \
       && curl -fsS --max-time 5 http://localhost:8081/      >/dev/null 2>&1; then
      return 0
    fi
    sleep 3
  done
  return 1
}

log "健康检查（最长 ${HEALTHCHECK_TIMEOUT_S}s）：后端 /health、用户端、管理端..."
if check_health; then
  echo "$IMAGE_TAG" > .last_deployed_tag
  log "✅ 部署成功，当前版本: $IMAGE_TAG"
  log "   备份文件: $BACKUP_FILE"
  $COMPOSE ps
  exit 0
fi

# ---------- 7. 健康检查失败：自动回滚到上一版本 ----------
log "❌ 健康检查未通过，自动回滚到上一版本: $OLD_TAG"
if [ "$OLD_TAG" = "未知" ]; then
  # 首次部署没有"上一版本"可回滚——如实报告，不假装恢复
  printf '[deploy][错误] 这是首次部署且健康检查失败，没有旧版本可回滚。\n' >&2
  printf '[deploy][错误] 数据已备份于: %s\n' "$BACKUP_FILE" >&2
  printf '[deploy][错误] 请检查: docker compose logs backend\n' >&2
  exit 2
fi

IMAGE_TAG="$OLD_TAG" $COMPOSE up -d || {
  printf '[deploy][错误] 回滚启动失败，需人工介入。数据备份于: %s\n' "$BACKUP_FILE" >&2
  exit 2
}

log "回滚完成，再次健康检查..."
if check_health; then
  log "✅ 已回滚到 $OLD_TAG，服务恢复。新版本 $IMAGE_TAG 部署失败，排查后可重试。"
  exit 1
fi

printf '[deploy][错误] 回滚后健康检查仍失败，需人工介入。数据备份于: %s\n' "$BACKUP_FILE" >&2
printf '[deploy][错误] 排查: docker compose logs backend / frontend-user / frontend-admin\n' >&2
exit 2
