# Runbook · Docker Desktop（Windows）故障处置

本机（Windows + Docker Desktop）实测出现过三类故障，处置顺序如下。

## 症状 A：引擎 API 全线 500 / 构建挂死

- `docker ps` 返回 500、构建无输出、站点失联。
- 多为长构建把 Desktop 代理层压死。

**处置**：重启 Docker Desktop
（杀 `Docker Desktop` / `com.docker.backend` 进程 → 启动 `Docker Desktop.exe` →
等引擎管道就绪约 1~2 分钟）。所有容器 `restart: unless-stopped` 会自动回来。

## 症状 B：容器内 HTTPS 被掐（SSL: UNEXPECTED_EOF_WHILE_READING）

- 主机访问外网正常、容器内 DNS 正常、纯 HTTP 正常，**仅 TLS 失败**；
- 典型诱因：compose 网络重建（改端口/重建容器）后代理层抽风。

**处置**：先 `docker restart` 目标容器；无效则重启 Docker Desktop。
⚠️ 对部署的启示：这是 **Windows Desktop 特有**问题，Linux 原生 Docker 无此层——
服务器上若出现同类症状，先查宿主机网络与防火墙，而不是怀疑应用。
缓解措施已落地：境外依赖（Open-Meteo）降为兜底，主源用国内直连的和风
（见 decisions/0001）。

## 症状 C：构建上下文巨大 / 构建被取消

- 构建卡在 "transferring context" 数百 MB。
- 根因几乎都是**构建目录里有 .venv / e2e-results / 截图**没被忽略。

**处置**：补 `.dockerignore`（backend 曾因 311MB 的 .venv，
上下文 238MB→33KB 后构建从"每次失败"变一分钟级）。
顺手 `git status` 检查这些文件是否也被 git 跟踪。

## 症状 D：`docker compose up` 后容器停在 Created

- 后台化/中断的 recreate 留下"Created"容器，页面自然失联。

**处置**：`docker ps -a` 确认 → `docker start <names>` 即可，
不必 force-recreate。

## 通用排查顺序

1. `docker ps -a`（谁挂了/谁没起）；
2. `docker logs <c> --tail 50`（启动即崩先看 traceback）；
3. 容器内直连测试（`python -c urllib...`）区分"应用错"还是"网络错"；
4. 主机 vs 容器对比测（DNS / HTTP / TLS 分层定位）；
5. 都不行 → 重启 Docker Desktop（杀进程再启，等管道就绪）。
