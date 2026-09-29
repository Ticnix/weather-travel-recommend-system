# 架构

> 历史演进细节见 [history/28天开发计划.md](history/28天开发计划.md)，本文只描述**当前形态**。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | FastAPI + SQLAlchemy(async) + Alembic + Celery(worker/beat) |
| 数据库 | PostgreSQL(TimescaleDB 连续聚合) + PostGIS + pgvector |
| 前端 | React + Vite + antd + TypeScript（PWA） |
| AI | DeepSeek（对话/工具）+ 智谱 GLM-4V（视觉）+ GLM embedding（RAG） |
| 天气 | **和风（主源，国内稳定）** + Open-Meteo（免费兜底：逐小时/AQI/简易预警） |

## 后端分层（backend/app/）

```
routers/      ← HTTP 层：参数校验、鉴权、统一响应包装 success()
services/     ← 业务层：全部业务逻辑；未传 db 时自建 AsyncSession（约定见 coding-style.md）
models/       ← ORM（models/__init__.py 必须注册新模型，否则 create_all 不建表）
schemas/      ← pydantic 出入参
tasks/        ← Celery 任务（早报/预警/行程冲突扫描，beat 每 10 分钟）
core/         ← config(.env)、deps(CurrentUser)、response、exceptions、observability
skills/       ← 可独立讲解的技能包（SKILL.md + references/ + scripts/）
```

**依赖方向**：routers → services → models。skills 反向被 services 调用
（`local_tools.py` 引 planner/reminder，`home_service` 引 outfit_engine）——
skills 的接口以调用方契约为准（重建事故见 decisions/0002）。

## 关键机制

- **多智能体对话**：`agent.py`（ReAct 决策）+ `multi_agent.py`（Supervisor 架构）
  + `local_tools.py`（进程内用户态工具：私有知识库检索、行程天气、AI 排程）。
  MCP 跑独立子进程（无用户态、公共工具），contextvars 跨不了进程——这是公私工具分流的根本原因。
- **统一响应**：`success()` 包 `{code, message, data}`；前端 `api/http.ts`
  拦截器**已解包一层**——前端拿到的直接是 `data` 本体（多解包一层是历史 bug）。
- **逐小时天气**：主源和风 `/weather/24h`（国内直连稳定），Open-Meteo 兜底；
  两源在 `weather_service.fetch_hourly` 归一化为 `HourlyPoint`
  （决策见 decisions/0001）。⚠️ `WeatherHistory` 表行没有 `temp_max` 等字段，
  打分必须用 `fetch_weather().daily`。
- **行程冲突预警**：celery beat 每 10 分钟 `assess_user_risks`，按类别推送
  （web push + 邮件），判重查发送记录，开关在 `notification_prefs`。
- **零成本原则**：非 AI 功能一律零 API 成本——海报是 canvas 纯排版、
  穿搭/提醒是规则模板、语音转写是本地 faster-whisper、逐小时/AQI 用免费源。

## 前端结构（frontend-user/src/）

```
pages/        路由页（Home/Itinerary/Chat/Profile/Notifications/Analysis/MyKnowledge…）
components/   可复用组件（HourlyChart 手写 SVG、PreferenceSettings…）
api/          http.ts 统一实例 + 按领域拆分的请求模块
utils/        prepareUpload(压缩)、itineraryShare(海报/分享)、useIsMobile
```

PWA：Service Worker 会缓存旧 bundle——**前端更新后用户需强刷**，验证时用
Playwright 记得 `serviceWorkers: 'block'`。

## 外部依赖与降级

| 依赖 | 用途 | 降级策略 |
| --- | --- | --- |
| 和风 | 实时/7天/逐小时/生活指数 | 免费源 Open-Meteo 兜底 |
| Open-Meteo | 逐小时、AQI、简易预警、历史回补 | 无（免费无 Key） |
| DeepSeek / 智谱 | 对话、视觉、embedding | 规则模板兜底（穿搭/提醒）；视觉被拒时自动禁用 10 分钟退 OCR |
| MCP 子进程 | 联网搜索、公共知识库 | 失败时回答降级为纯 LLM |
