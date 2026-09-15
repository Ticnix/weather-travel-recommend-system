# 基于气象大数据的出行推荐系统

[![CI](https://github.com/Ticnix/weather-travel-recommend-system/actions/workflows/ci.yml/badge.svg)](https://github.com/Ticnix/weather-travel-recommend-system/actions/workflows/ci.yml)

面向**广州市**的气象大数据 + AI 智能体出行推荐平台。以「多模 PostgreSQL」为数据底座，
用 **LangGraph + MCP + RAG + Skill** 构建能查天气、做攻略、规划路线、推荐穿搭的 AI 助手，
并配套完整的 C 端用户站与 B 端管理后台。

> **自动化质量保障**：442 个测试用例（后端 pytest 379 + 前端 Vitest 41 + E2E Playwright 22），
> 每次提交自动跑 lint → test → build 三关，任一失败即拦截。
> 想了解"测试到底在干嘛"→ 见 [测试入门指南.md](./测试入门指南.md)。

---

## 一、核心功能

### 用户端（C 端）
| 功能 | 说明 |
| --- | --- |
| 天气首页 | 实时天气卡片 + 7 天预报 |
| AI 对话 | SSE 流式输出，打字机效果，支持多轮上下文记忆 |
| 智能推荐 | 出行规划（真实高德路线）与穿搭推荐双 Tab |
| 气象资讯 | 列表 / 详情 / 分类筛选 |
| 意见反馈 | 提交反馈并跟踪处理状态 |
| 登录注册 | JWT 鉴权，登录后对话历史持久化 |

### 管理端（B 端）
- 登录 + 路由权限守卫
- 气象大数据管理：筛选、批量操作、导出
- 资讯公告 CRUD
- 用户反馈：状态流转 + 回复
- 气象时序统计：ECharts 图表
- 数据清洗：CSV 上传、任务日志、结果下载

### AI 能力
- **LangGraph Agent**：意图识别 → 工具决策 → 结果整合的状态机
- **MCP 工具层**：天气、预报、资讯、知识库等工具，Agent 自动选择调用
- **RAG 知识库**：15 篇广州本地文档（景点/美食/交通/穿搭/气候…）向量化语义检索
- **Skill**：出行规划、穿搭推荐、行程天气提醒
- **联网搜索**：Tavily 优先，DuckDuckGo 兜底
- **用户私有知识库**：多租户隔离，仅本人可检索

---

## 二、技术栈

| 层 | 选型 |
| --- | --- |
| 用户端 | React 19 + Vite + TypeScript + Ant Design + React Router |
| 管理端 | Vue 3 + Vite + TypeScript + Element Plus + Pinia + ECharts |
| 后端 | FastAPI + SQLAlchemy 2.0 异步 ORM + Alembic |
| 数据库 | PostgreSQL 17 + TimescaleDB（时序）+ PostGIS（地理）+ pgvector（向量） |
| 缓存/队列 | Redis + Celery |
| AI | LangGraph + MCP + RAG；LLM 支持 DeepSeek/Qwen/智谱/OpenAI/Kimi/Ollama 多模型切换 |
| Embedding | 智谱 embedding-3（1024 维，与 `Vector(1024)` 对齐） |
| 外部数据源 | 和风天气（主）/ Open-Meteo（兜底）、高德地图、Tavily |

---

## 三、目录结构

```
.
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── core/                # 配置 / 统一响应 / 全局异常 / JWT / 鉴权依赖 / Redis 缓存
│   │   ├── db/                  # 异步引擎与会话
│   │   ├── models/              # ORM 模型
│   │   ├── routers/             # 接口：users news feedback weather clean knowledge chat recommend itinerary
│   │   ├── schemas/             # Pydantic 模型
│   │   ├── services/            # 业务层：agent / mcp_client / rag_service / llm_client / amap_client ...
│   │   ├── tasks/               # Celery 异步任务
│   │   ├── scripts/             # init_db / ai_demo
│   │   └── celery_app.py        # Celery 应用与 beat 定时
│   ├── mcp_server/              # MCP Server（工具定义与实现）
│   ├── skills/                  # Skill：travel_planning / outfit_recommend / itinerary_reminder
│   ├── knowledge_base/          # RAG 知识库原始文档（15 篇 md）
│   └── alembic/                 # 数据库迁移
├── frontend-user/               # C 端 React19
├── frontend-admin/              # B 端 Vue3
├── docker-compose.yml           # 一键编排全部服务
└── Dockerfile.pg                # 含三大扩展的 PostgreSQL 镜像
```

---

## 四、快速开始

### 方式一：Docker 一键启动（推荐）

```bash
docker compose up -d --build
```

| 服务 | 地址 |
| --- | --- |
| 用户端 | http://localhost:8080 |
| 管理端 | http://localhost:8081 |
| 后端 API 文档 | http://localhost:8000/docs |

> 首次启动需构建 PostgreSQL 自定义镜像（安装 PostGIS + TimescaleDB），耗时较长。

### 方式二：本地开发

**1. 启动依赖服务**

```bash
docker compose up -d postgres redis
```

**2. 初始化数据库**

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Linux: source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head            # 或 python -m app.scripts.init_db
```

**3. 配置环境变量**

复制 `backend/.env` 并填写需要的 Key（详见下节）。**未配置 Key 的功能会自动降级**，
不会导致启动失败。

**4. 启动服务**

```bash
# 后端（必须用 8001，前端 vite proxy 已指向该端口）
uvicorn app.main:app --host 127.0.0.1 --port 8001

# Celery worker（Windows 需加 -P solo）
celery -A app.celery_app worker -l info -P solo

cd frontend-user  && npm install && npm run dev    # 5173
cd frontend-admin && npm install && npm run dev    # 5174
```

**5. 构建知识库索引**

登录后调用（或 Swagger 中带 Token 调用）：

```bash
POST /api/v1/knowledge/index      # 同步
POST /api/v1/knowledge/index/async # 异步（Celery）
```

默认管理员账号：`admin` / `Admin@123456`

---

## 五、环境变量（backend/.env）

| 变量 | 说明 | 是否必填 |
| --- | --- | --- |
| `DB_URL` | PostgreSQL 异步连接串 | 是 |
| `REDIS_URL` | Redis 地址（Celery broker + 业务缓存） | 是 |
| `LLM_PROVIDER` | 对话模型提供商：`deepseek`/`qwen`/`zhipu`/`openai`/`moonshot`/`ollama` | 否（默认 deepseek） |
| `DEEPSEEK_API_KEY` | DeepSeek Key | 使用 DeepSeek 时必填 |
| `ZHIPU_API_KEY` | 智谱 Key（Embedding 与 GLM 共用） | **RAG 检索必填** |
| `WEATHER_PROVIDER` | `qweather` / `open_meteo` | 否（默认 open_meteo，免 Key） |
| `QWEATHER_API_KEY` | 和风天气 Key（有官方预警） | 否 |
| `AMAP_API_KEY` | 高德 Web 服务 Key（真实路线规划） | 出行推荐需要 |
| `TAVILY_API_KEY` | 联网搜索 Key | 否（无则降级 DuckDuckGo） |
| `JWT_SECRET` | JWT 签名密钥 | 生产必改 |

> 所有 Key **仅存于后端 `.env`**，已加入 `.gitignore`，不会提交到仓库或暴露给前端。

---

## 六、架构说明

### 数据链路

```
外部数据源（和风 / Open-Meteo）
   ↓ Celery 定时同步
weather_history（TimescaleDB 超表）
   ↓ 清洗 / 聚合
业务接口（Redis 缓存）→ 前端展示
```

### AI 对话链路

```
用户提问
  ↓ 意图识别（强关键词预判 → LLM 分类 → 弱关键词兜底）
  ↓ 命中工具意图则绑定 MCP + 本地工具
LangGraph：agent ⇄ tools（ReAct 循环）
  ↓ 整合工具结果
SSE 逐 token 流式返回
```

### 降级策略（任一层故障都不会 500）

| 环节 | 降级方案 |
| --- | --- |
| LLM 调用失败 | 意图识别改关键词；生成节点返回友好提示 |
| 意图识别不稳定 | 强关键词直接定意图，绕过 LLM |
| 和风天气失败 | 自动切换 Open-Meteo |
| Redis 不可用 | 缓存静默跳过，业务逻辑不受影响 |
| 联网搜索失败 | Tavily → DuckDuckGo |
| Embedding 失败 | 索引/检索返回空并给出提示 |

---

## 七、常用接口

| 分组 | 接口 |
| --- | --- |
| 用户 | `/api/v1/users/register`、`/login`、`/me` |
| 天气 | `/api/v1/weather/current`、`/forecast`、`/history`、`/stats`、`/sync` |
| 资讯 | `/api/v1/news` |
| 反馈 | `/api/v1/feedback` |
| 清洗 | `/api/v1/clean/upload`、`/tasks` |
| 知识库 | `/api/v1/knowledge/index`、`/search` |
| 对话 | `/api/v1/chat`、`/api/v1/chat/stream`（SSE） |
| 推荐 | `/api/v1/recommend/travel`、`/recommend/outfit` |

完整列表见 Swagger：`http://localhost:8000/docs`

---

## 八、常见问题

**Q：后端必须用 8001 端口吗？**
A：本地开发是的，两个前端的 vite proxy 都指向 8001。容器内为 8000，由 Nginx 转发。

**Q：没配 Key 能跑起来吗？**
A：可以。天气默认走免 Key 的 Open-Meteo；AI 相关功能会在调用时降级并返回友好提示，
其余模块（资讯、反馈、气象数据）完全不受影响。

**Q：为什么 `weather_history` 是超表？**
A：气象数据是典型时序数据，用 TimescaleDB 超表按 `time` 自动分区，
写入与按时间范围聚合查询性能更好。

**Q：Windows 上 Celery 启动报错？**
A：用 `celery -A app.celery_app worker -l info -P solo`，prefork 池在 Windows 不可用。

---

## 九、开发进度

28 天计划详见 [28天开发计划.md](./28天开发计划.md)，逐日记录见 [工作日志.md](./工作日志.md)。
面试向的技术梳理见 [面试宝典.md](./面试宝典.md) 与 [Skill技术解析.md](./Skill技术解析.md)。
技术原理与踩坑剖析见 [知识点剖析.md](./知识点剖析.md)。
**零基础想搞懂"自动化测试在干嘛"** → [测试入门指南.md](./测试入门指南.md)
（用大白话讲清测试是什么，以及项目里 442 个测试用例分别在守什么）。
