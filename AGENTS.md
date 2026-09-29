# AGENTS.md

广州天气旅行助手 —— 天气 × 行程的个性化推荐系统（FastAPI + React + TimescaleDB + 多智能体）。

**本文件只告诉你去哪找信息，细节一律看对应文档。**

## 常用命令

| 用途 | 命令 |
| --- | --- |
| 启动全套 | `docker compose up -d --build` |
| 后端测试 | `docker compose exec -T backend pytest -q` |
| 前端类型检查 | `cd frontend-user && tsc -b`（**必须过**，IDE lint 比 tsc 松） |
| 前端单元测试 | `cd frontend-user && npm test` |
| Lint | `ruff check backend/app` / `npm run lint` |
| 数据库迁移 | `docker compose run --rm backend alembic upgrade head` |
| 本地前端开发 | `npm run dev`（API 代理默认 8000，见 vite.config.ts） |

## 目录地图

| 要找什么 | 去哪 |
| --- | --- |
| 架构、模块边界、外部依赖、数据流 | [docs/architecture.md](docs/architecture.md) |
| 测试怎么跑、验证清单 | [docs/testing.md](docs/testing.md) |
| 代码规范（前后端约定与已知陷阱） | [docs/coding-style.md](docs/coding-style.md) |
| 功能清单、竞争优势 | [docs/product/features.md](docs/product/features.md) |
| 待办与规划 | [docs/product/roadmap.md](docs/product/roadmap.md) |
| 部署步骤 | [docs/runbooks/deploy.md](docs/runbooks/deploy.md) |
| 故障处置（Docker/网络） | [docs/runbooks/](docs/runbooks/) |
| 关键技术决策及原因 | [docs/decisions/](docs/decisions/) |
| 全部历史：28 天开发日志、踩坑记录 | [docs/history/](docs/history/)（原 28天开发计划.md / 工作日志.md / 知识点剖析.md） |
| 面试/求职材料 | [博客/](博客/)、简历项目经历-AI出行推荐系统.md |

## Done criteria

一个功能算"完成"必须同时满足：

1. `tsc -b` 与 `ruff check` 通过；
2. **真实调用过接口或页面**（静态检查会漏掉 NameError / 响应解包层级 / antd v6 API 差异，历史教训见 docs/coding-style.md）；
3. 有数据竞态的接口写了并发测试；
4. 文档同步（本目录对应文件 + history 补一段）；
5. `git add -A && git commit`（身份已是 Ticnix，见仓库级 git config）。

## 三条铁律（踩过坑的）

1. **改完必须真跑一次**——静态检查全过也可能 NameError/500；
2. **新文件落盘前先确认不存在**（write 会静默覆盖，recommend.py 曾被这样覆盖）；
3. **恢复文件只用 `git checkout --`**，PowerShell 重定向会写出 UTF-16。
