# Runbook · 部署

## 全新服务器部署

1. **准备 `backend/.env`**（参照本地文件，但必须更换）：
   - `JWT_SECRET` = 新随机值（默认 `change-me` 在公开代码里可见）；
   - 数据库密码；`QWEATHER_API_KEY` / `ZHIPU_API_KEY` / `DEEPSEEK_API_KEY`；
   - 生产 SMTP（不用 Mailhog）。
2. `docker compose up -d --build`
   - 语音模型构建时预下载（`timeout 900` 保护，超时跳过、首次使用自动重下）；
3. **数据库**：
   - 全新空库：应用启动 `create_all` 自动建表，无需迁移；
   - 已存在的老库：`docker compose run --rm backend alembic upgrade head`
     （有 `0012_notification_risk`、`0013_user_preferences`）；
4. **立即登录改掉 admin 密码**（`init_db.py` 播种 `admin / Admin@123456`，
   默认口令在公开仓库可见）；
5. 冒烟：登录 → 首页 24h 曲线（≥20 点）/ AQI 徽标 → 行程徽标 → 聊天。

## 端口策略（已固化进 compose）

- 对外：`8080`（用户端）、`8081`（管理端）；
- 仅本机：`5432` pg、`6379` redis（无密码！）、`8000` 后端、`1025/8025` mailhog；
- 原因与决策记录：[../decisions/0004-infra-ports-loopback.md](../decisions/0004-infra-ports-loopback.md)

## 升级已有部署

1. `git pull`
2. 有迁移则 `docker compose run --rm backend alembic upgrade head`（**先迁移后重建**）；
3. `docker compose up -d --build`
4. 冒烟：登录 + `/weather/hourly` 24 点 + 行程徽标。

## 回滚

`git checkout <上一个 tag/commit>` → `docker compose up -d --build`；
迁移回滚 `alembic downgrade -1`（0013 只建表，回滚无损）。
