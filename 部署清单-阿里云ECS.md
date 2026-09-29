# 部署清单 —— 阿里云 ECS（116.62.155.77）

> 机器现状：2核4G 共享型，Windows Server 2022，**试用到期 2026-10-13**。
> 目标：换成 Ubuntu → 装 Docker → 跑 docker compose 全套。

## 零、一键部署（推荐，省去下面手动步骤）

换好 Ubuntu 并 SSH 登录后，只跑这一行，剩下的全自动（装 Docker、加 swap、拉代码、生成密钥、构建、初始化数据库）：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Ticnix/weather-travel-recommend-system/main/deploy-ecs.sh)
```

> 若 GitHub 拉脚本慢，可先把 `deploy-ecs.sh` 和 `docker-compose.prod.yml` 用 scp 传上去再 `bash deploy-ecs.sh`。
> 脚本内部已包含下面第 2～7 步的全部逻辑，手动分步版保留作为排查参考。

---

## 第 0 步：更换操作系统为 Ubuntu（必须，会清空磁盘）

新机器没有数据，直接换：

1. ECS 控制台 → 实例列表 → 找到 `iZ0n8odie2czyyZ` → **停止**（等状态变「已停止」）
2. **更多** → **磁盘和镜像** → **更换操作系统**
3. 镜像选 **Ubuntu 22.04 64位**，设置 root 密码（记住它）
4. 等几分钟启动完成

> 为什么必须换：Docker 只能跑 Linux 容器，Windows 上装 Docker Desktop 需要嵌套虚拟化（这台不支持）；
> 且 Windows Server 空载就吃 ~2G 内存 + CPU 94% 基本是它贡献的。

## 第 1 步：安全组放行端口

实例 → **安全组** → 配置规则 → **入方向** 添加：

| 端口 | 用途 | 授权对象 |
|---|---|---|
| 22 | SSH 登录 | 0.0.0.0/0（或限定你的 IP 更安全） |
| 8000 | 后端 API | 0.0.0.0/0 |
| 8080 | 用户端 | 0.0.0.0/0 |
| 8081 | 管理端 | 0.0.0.0/0 |

> **不要放行** 5432(PostgreSQL)、6379(Redis)、8025(MailHog)。

## 第 2 步：SSH 登录 + 装 Docker

本地 Git Bash 执行：

```bash
ssh root@116.62.155.77
```

登录后（阿里云国内源装 Docker，几秒到几分钟）：

```bash
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
systemctl enable --now docker
docker compose version   # 验证 compose v2 可用
```

## 第 3 步：拿到代码

**首选：服务器上直接 clone**（阿里云访问 GitHub 一般能通，慢就多试）：

```bash
cd /root
git clone https://github.com/Ticnix/weather-travel-recommend-system.git
cd weather-travel-recommend-system
```

**备选：clone 慢/不通时，本地打包上传**（本地 Git Bash 执行）：

```bash
cd /d/myproject/weather-travel-recommend-system
git archive --format=zip -o /tmp/src.zip HEAD
scp /tmp/src.zip root@116.62.155.77:/root/src.zip
# 然后到服务器上：apt install -y unzip && unzip src.zip -d weather-travel-recommend-system
```

> ⚠️ `git archive` 不会包含 `.env`（被 gitignore 了），下一步手动创建。

## 第 4 步：创建生产 .env（3 个必改项）

本地打开 `backend/.env`，复制内容，在服务器上创建：

```bash
vim backend/.env   # 粘贴本地 .env 内容，改下面三处
```

| 必改 | 怎么改 |
|---|---|
| `JWT_SECRET` | 换成随机长串，服务器上执行 `openssl rand -hex 32` 生成 |
| PG 密码 | 同步改 `docker-compose.yml`：postgres 的 `POSTGRES_PASSWORD` + backend/celery/celery-beat 三处 `DB_URL` 里的密码，共 4 处保持一致 |
| 管理员密码 | 部署后登录管理端改掉 `Admin@123456` |

> ⚠️ `backend/.env` 里的真实 Key（DeepSeek/智谱等）注意保密，别提交到仓库。

## 第 5 步：加 swap 再构建（2核4G 必须，否则构建易 OOM）

```bash
fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
free -h   # 确认 swap 4G 生效
```

## 第 6 步：构建 + 启动

```bash
cd /root/weather-travel-recommend-system
docker compose up -d --build
```

> PG 自定义镜像（装三大扩展）首次构建较久；如果中途断/OOM，分开构建：
> `docker compose build postgres && docker compose build backend && docker compose build frontend-user frontend-admin`
> 再 `docker compose up -d`。

## 第 7 步：初始化数据库 + 建知识库索引

```bash
docker compose exec backend alembic upgrade head   # 建表/迁移
```

浏览器打开 `http://116.62.155.77:8000/docs`，带管理员 Token 调用：
`POST /api/v1/knowledge/index` 建 RAG 索引。

## 第 8 步：验收

| 入口 | 地址 |
|---|---|
| 用户端 | http://116.62.155.77:8080 |
| 管理端 | http://116.62.155.77:8081 |
| API 文档 | http://116.62.155.77:8000/docs |

## 收尾（重要）

- [ ] **禁用 mailhog**：`docker compose stop mailhog`（它是验收工具，不该在公网跑；或直接从 compose 删掉该服务）
- [ ] **改管理员默认密码**
- [ ] `docker compose ps` 确认 7 个服务全 Up；`docker compose logs backend --tail 50` 查无报错
- [ ] **试用 2026-10-13 到期**：到期前决定续费/转包月，或提前 `./deploy.sh` 里的 pg_dump 逻辑备份数据（`docker compose exec -T postgres pg_dump -U admin -d weather_db | gzip > backup.sql.gz`）

## 以后更新代码怎么发版

```bash
cd /root/weather-travel-recommend-system
git pull
docker compose up -d --build backend celery celery-beat frontend-user frontend-admin
```
