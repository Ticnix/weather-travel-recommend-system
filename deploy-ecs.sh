#!/usr/bin/env bash
# ============================================================================
# deploy-ecs.sh —— 阿里云 ECS（全新 Ubuntu 22.04）一键部署
#
# 前置（你只需在网页上做两件事）：
#   1. 控制台把实例系统换成 Ubuntu 22.04（换系统会清盘，新机无所谓）
#   2. SSH 登录：ssh root@<你的公网IP>
#   3. 粘贴运行本脚本：  bash <(curl -fsSL <本脚本地址>)   或  把本文件 scp 上去跑
#
# 脚本会做完剩下所有事：装 Docker → 加 swap → 拉代码 → 生成密钥 →
# 构建镜像 → 起服务 → 初始化数据库 → 输出访问地址。
#
# 设计：全程非交互、可重跑（已装的步骤会跳过）。
# ============================================================================
set -euo pipefail

REPO_URL="https://github.com/Ticnix/weather-travel-recommend-system.git"
REPO_DIR="/root/weather-travel-recommend-system"
PROJECT_NAME="weather"

log()  { printf '\033[32m[deploy]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请使用 root 运行（或 sudo -i 后重试）"

# ---------- 1. 安装 Docker + compose 插件 ----------
if command -v docker >/dev/null 2>&1; then
  log "Docker 已安装，跳过"
else
  log "安装 Docker（阿里云镜像源）..."
  curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
fi
systemctl enable --now docker
if ! docker compose version >/dev/null 2>&1; then
  log "安装 docker-compose-plugin..."
  apt-get update -qq && apt-get install -y docker-compose-plugin
fi
docker compose version >/dev/null 2>&1 || die "docker compose 仍不可用"
log "Docker 就绪：$(docker --version)"

# ---------- 2. 加 4G swap（2核4G 构建必加，防 OOM）----------
if swapon --show | grep -q '/swapfile'; then
  log "swap 已存在，跳过"
else
  log "创建 4G swap..."
  fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
free -h | head -2

# ---------- 3. 拉取代码 ----------
if [ -d "$REPO_DIR/.git" ]; then
  log "代码目录已存在，git pull..."
  git -C "$REPO_DIR" pull --ff-only
else
  log "克隆代码 → $REPO_DIR"
  if ! git clone "$REPO_URL" "$REPO_DIR"; then
    die "GitHub 克隆失败。备选：在本机执行
      cd <项目根> && git archive --format=zip -o /tmp/src.zip HEAD
      再 scp /tmp/src.zip root@<IP>:/root/src.zip
      然后 ssh 进去：mkdir -p $REPO_DIR && unzip /root/src.zip -d $REPO_DIR"
  fi
fi
cd "$REPO_DIR"

# ---------- 4. 生成生产配置（.env.prod + 随机密钥）----------
if [ ! -f backend/.env.prod ]; then
  log "基于模板生成 backend/.env.prod..."
  cp backend/.env.prod.example backend/.env.prod
  # JWT_SECRET 填随机串
  JWT_SECRET="$(openssl rand -hex 32)"
  sed -i "s|^JWT_SECRET=.*|JWT_SECRET=${JWT_SECRET}|" backend/.env.prod
  # 把生成的 JWT 记到部署信息文件（仅 root 可读），方便日后排查
  echo "JWT_SECRET=$JWT_SECRET" > /root/.deploy-secrets
fi
# 数据库密码：每次运行用同一个（落到 /root/.deploy-secrets，避免重建时不一致）
if [ -f /root/.deploy-secrets ] && grep -q '^PG_PASSWORD=' /root/.deploy-secrets; then
  PG_PASSWORD="$(grep '^PG_PASSWORD=' /root/.deploy-secrets | cut -d= -f2)"
else
  PG_PASSWORD="$(openssl rand -hex 16)"
  echo "PG_PASSWORD=$PG_PASSWORD" >> /root/.deploy-secrets
fi
chmod 600 /root/.deploy-secrets
log "已生成密钥，存于 /root/.deploy-secrets（请妥善保管，重装系统会丢失）"

# ---------- 5. 构建 + 启动 ----------
log "构建并启动全部服务（首次约 10-20 分钟，PG 镜像装三大扩展较慢）..."
ENV_FILE=./backend/.env.prod PG_PASSWORD="$PG_PASSWORD" \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# ---------- 6. 等 PostgreSQL 就绪 → 初始化数据库 ----------
log "等待 PostgreSQL 就绪..."
for i in $(seq 1 30); do
  if docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
       pg_isready -U admin -d weather_db >/dev/null 2>&1; then
    break
  fi
  sleep 3
done
log "执行数据库迁移（alembic upgrade head）..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backend \
  alembic upgrade head || warn "alembic 失败，请排查：docker compose logs backend"

# ---------- 7. 输出访问信息 ----------
PUB_IP="$(curl -fsS --max-time 5 ip.sb || curl -fsS --max-time 5 ifconfig.me || echo '<你的公网IP>')"
echo
log "========== 部署完成 =========="
log "用户端:   http://${PUB_IP}:8080"
log "管理端:   http://${PUB_IP}:8081"
log "API文档:  http://${PUB_IP}:8000/docs"
echo
warn "下一步：登录管理端改掉默认管理员密码 Admin@123456"
warn "建 RAG 知识库索引：用管理员 Token 调 POST /api/v1/knowledge/index"
warn "注意：当前为明文 HTTP；要 HTTPS 时再挂 Caddy，我可给你配置"
warn "试用实例 2026-10-13 到期，到期前请 pg_dump 备份或续费"
