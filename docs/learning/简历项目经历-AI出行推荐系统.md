# 简历项目经历 — 气象大数据 + AI Agent 出行推荐系统

> 项目源码：https://github.com/Ticnix/weather-travel-recommend-system
> 技术栈：FastAPI · LangGraph/MCP/RAG · PostgreSQL(TimescaleDB/pgvector/PostGIS) · Redis/Celery · React 19 · Vue 3
> 所有数字与细节均来自仓库实测，面试可溯源。

---

## 一、一句话概述（通用版）

独立设计并交付「气象大数据 + AI Agent」全栈平台：LangGraph 状态机编排智能体，单实例 PostgreSQL 承载四类工作负载（OLTP/TimescaleDB/pgvector/PostGIS），React 19 + Vue 3 双端，71 次提交 · 442 测试用例 · CI 门禁。

---

## 二、前端版

### 简历 Bullet（直接粘贴）

- 自研 **LLM 流式渲染管线**：fetch + ReadableStream 增量解析 SSE，对 chunk 双形态（字符串 / content 片段数组）做归一化，AbortController 中断 + 异常降级 UI，**TTFT 从整段等待降到首字毫秒级**
- 独立交付 **React 19 + Vue 3 双端工程**：C 端 PWA 离线缓存 + 打字机流式对话；B 端 ECharts 气象时序可视化 + 批量数据管理，双端 TypeScript 严格模式并行演进
- 构建**零网络依赖的前端测试体系**：Vitest 41 单测 + Playwright 22 条 E2E 关键路径 + GitHub Actions lint/test/build 三关门禁，全仓 442 用例确定性 49s 跑完，回归问题提交即拦截

### STAR 展开（面试口述备稿）

**1. LLM 流式渲染管线**
- **S**：LLM 推理 TTFT 高，整段返回导致对话体验断裂
- **T**：设计端侧流式渲染方案
- **A**：fetch + ReadableStream 增量解析 SSE；对 astream chunk 的两种形态（str / 片段数组）做归一化层；AbortController 支持用户中途中断；解析异常走降级 UI 而非白屏
- **R**：首字毫秒级可见，配合多轮上下文达到原生 AI 产品级对话体验

**2. React 19 + Vue 3 双端工程**
- **S/T**：一人承担 C 端用户站与 B 端管理后台
- **A**：C 端 React 19 + Vite + vite-plugin-pwa 离线缓存；B 端 Vue 3 + Element Plus + ECharts 气象时序可视化与 CSV 数据清洗管理
- **R**：双端并行交付零阻塞，均过严格模式与 ESLint 规范

**3. 零网络依赖测试体系**
- **S**：AI 项目外部依赖多，「改一处崩一片」且回归慢
- **T**：搭建确定性测试体系
- **A**：Vitest + Testing Library 组件单测；Playwright 22 条 E2E 关键路径；CI 三关门禁
- **R**：442 用例离线 49s 确定性跑完，不依赖任何外部服务，提交即拦截

---

## 三、全栈版

### 简历 Bullet（直接粘贴）

- 基于 **LangGraph 条件边构建 Agent 状态机**（意图识别 → 工具决策 → 结果整合 → 错误兜底），将 LLM 视为不可信供应商：**纯函数审计输出 + extract_json 三级容错解析 + contextvars 实现异步并发下的用户态零串扰**，支持 AGENT_MODE 一键回退规则引擎
- 以 **MCP 协议将 7 个工具从 Agent 主循环剥离实现进程级解耦**；**单实例 PostgreSQL 承载四类工作负载**（业务 OLTP + TimescaleDB 时序 + pgvector 向量 + PostGIS 地理），多租户 RAG 强制 user_id 向量预过滤，检索零越权
- 设计 **OpenAI 兼容多厂商适配层**（DeepSeek/Qwen/智谱/Kimi/Ollama 换三个字符串即切换），以 function_calling 替代 json_schema 绕开厂商兼容性故障，配套**搜索兜底 / 视觉服务 600s TTL 熔断自愈 / Celery 任务重试的四级降级链路**

### STAR 展开（面试口述备稿）

**1. Agent 状态机与 LLM 不可信设计**
- **S**：LLM 输出不可控、异步并发下用户态易串扰、规则引擎与智能体需随时切换
- **T**：设计 Agent 编排层与防御性解析
- **A**：LangGraph 条件边状态机；纯函数审计 LLM 输出（LLM 是供应商不是下属）；extract_json 三级解析（剥围栏 → 截取首尾大括号 → 兜底）；contextvars 隔离每请求用户态；AGENT_MODE 一键回退
- **R**：单点故障不影响回复可用性，并发用户零串扰，智能体/规则模式可灰度切换

**2. MCP 工具层 + 单库多工作负载**
- **S**：Agent 与工具强耦合；向量/时序/地理/业务数据多引擎堆叠成本高
- **T**：工具层解耦 + 数据底座选型
- **A**：MCP 协议剥离 7 个工具（天气/预报/资讯/知识库等）；单 PostgreSQL 实例同时承载 OLTP、TimescaleDB hypertable、pgvector、PostGIS；RAG 检索强制 WHERE user_id
- **R**：加工具/换厂商零侵入 Agent 代码，省掉 3+ 个独立数据组件的运维成本，检索零越权

**3. 多模型适配与四级降级**
- **S**：绑定单一 LLM 供应商风险高；不同厂商接口行为不一致（如某厂商不支持 json_schema 直接 400）
- **T**：模型接入层与容错体系
- **A**：_PROVIDERS 三元组适配层；以 function_calling 方式做结构化输出绕开兼容性故障；Tavily→DDG 搜索兜底；视觉服务故障 600s TTL 熔断、到期自愈重试；Celery 异步任务重试退避
- **R**：四级降级保证外部依赖故障时全程可用，442 用例 + CI 门禁验证

---

## 四、面试追问弹药库（真实数据锚点）

| 追问点 | 可回溯的实证 |
| --- | --- |
| 「四类工作负载怎么理解？」 | PostgreSQL 17 单实例：业务表 OLTP + TimescaleDB 气象时序 + pgvector 1024 维向量 + PostGIS 地理（docker-compose.yml / alembic 迁移可查） |
| 「contextvars 隔离是什么？」 | 异步并发下每请求用户态隔离，避免连接池复用导致串扰（03 篇博客有完整推导） |
| 「LLM 不可信怎么落地？」 | 纯函数审计 + extract_json 三级解析；DeepSeek 不支持 response_format=json_schema 返回 400 的真实事故，改用 function_calling 解决 |
| 「600s TTL 熔断自愈？」 | 视觉 Key 失效时 mark_vision_broken 短路 600s，到期自动重试视觉路径，避免永久降级 |
| 「MCP 解耦了哪 7 个工具？」 | mcp_server/tools.py 逐字可查，工具名三处一致是硬约束 |
| 「442 测试构成？」 | pytest 379 + Vitest 41 + Playwright 22，外部依赖全 mock，零网络确定性执行 |
| 「71 次提交怎么来的？」 | 42 天 DayN 标记，日历跨度仅 26 天，git log 可查 |
| 「一键回退是什么？」 | AGENT_MODE 开关在智能体与规则引擎间切换，智能体异常时回退到确定性规则路径 |

---

## 五、使用建议

1. **区分度来自具体性**：满屏「RAG + Agent」的简历里，「单实例 PG 四类工作负载」「contextvars 用户态隔离」「json_schema 400 兼容性事故」这种细节才是面试官会停下来问的东西。
2. **前端岗**：第一条 SSE 管线 bullet 是最大差异化，务必放最前。
3. **AI 应用/后端岗**：全栈版三条分别覆盖「编排架构 / 数据架构 / 稳定性架构」三个维度，正好对应面试官的三类追问。
4. 每条 bullet 控制在一行半以内；细节留给弹药库表，被追问时逐条抛出，形成「越问越深」的体验。
