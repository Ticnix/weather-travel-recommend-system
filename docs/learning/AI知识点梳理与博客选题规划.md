# AI 知识点梳理与博客选题规划

> 对象：`weather-travel-recommend-system`（广州气象大数据 + AI 智能体出行推荐系统）
> 目的：把项目里散落在代码中的 AI 知识点抽出来，形成可独立成篇的技术博客选题池。
> 原则：**只收录"新"的知识点**——即 2024 年后的主流 AI 工程范式（Agent / MCP / Skills / 多租户 RAG / 上下文隔离 / 流式协议），不写"什么是大模型""如何调 API"这类过期内容。

---

## 一、项目 AI 全景（一句话链路）

```
用户提问
  │
  ├─ 意图识别：强关键词预判 → LLM 分类 → 弱关键词兜底          （三级降级）
  │
  └─ LangGraph 状态机
        START → classify_intent ─┬→ handle_error → END
                                └→ agent(LLM 决策) ⇄ tools(N×)
                                            │
                    ┌───────────────────────┴───────────────────────┐
                    │ MCP 工具（独立进程，无状态公共能力）            │
                    │ get_weather / get_forecast / search_news      │
                    │ search_knowledge(RAG) / web_search(Tavily)    │
                    │ plan_travel_route(Skill) / recommend_outfit   │
                    ├───────────────────────────────────────────────┤
                    │ 本地工具（Agent 进程内，带用户态）              │
                    │ search_my_plans / check_itinerary_weather     │
                    └───────────────────────────────────────────────┘
                                            │
                                     LLM 整合 → SSE 逐 token 流式返回
```

**技术密度分布**（按代码量估算）：

| 层 | 关键文件 | AI 含量 |
| --- | --- | --- |
| Agent 编排 | `app/services/agent.py` | ★★★★★ |
| MCP 工具 | `mcp_server/server.py`、`mcp_server/tools.py`、`app/services/mcp_client.py` | ★★★★★ |
| RAG 检索 | `rag_service.py`、`embedding_client.py`、`knowledge_loader.py`、`user_knowledge_service.py` | ★★★★★ |
| Skill 封装 | `backend/skills/*`、`skill_loader.py` | ★★★★☆ |
| LLM 接入 | `llm_client.py` | ★★★☆☆ |
| 上下文隔离 | `user_context.py`、`local_tools.py` | ★★★★☆ |
| 流式/多轮 | `routers/chat.py`、`chat_history_service.py`、`frontend-user/src/api/chat.ts` | ★★★★☆ |
| 搜索增强 | `web_search_service.py`、`outfit_inspiration.py`、`article_extractor.py` | ★★★☆☆ |

---

## 二、AI 知识点清单（9 大模块 · 42 个知识点）

### 模块 1 · LLM 接入与提示工程（5 个）

| 编号 | 知识点 | 代码位置 | 核心要点 | 新颖度 |
| --- | --- | --- | --- | --- |
| **1.1** | **多提供商 LLM 抽象层** | `llm_client.py` `_PROVIDERS` | 只接「OpenAI 兼容格式」（DeepSeek/Qwen/GLM/OpenAI/Moonshot/Ollama），统一走 `ChatOpenAI`，靠 `base_url + api_key + model` 三字段切换；避免为每个厂商写适配器。多实例缓存互不干扰 | ★★★★ |
| **1.2** | **空 Key 优雅降级** | `llm_client.py:get_llm` | 未配 Key 时用 `sk-placeholder` 实例化，**不崩溃**，真调用时才报鉴权错，由图内兜底节点统一处理 | ★★★★ |
| **1.3** | **提示词即决策引擎** | `agent.py:GENERATE_SYSTEM_PROMPT` | 不用 if-else 硬编码流程，把 9 条决策规则（何时调哪个工具、何时反问、何时直答）写进系统提示词，让 LLM 自主路由 | ★★★★ |
| **1.4** | **复合问题的多工具协同** | 同上规则 1 | "明天去广州塔穿什么、怎么去" → 一次触发 `get_weather` + `recommend_outfit` + `plan_travel_route` 三工具链，最后整合，不许只答一半 | ★★★★ |
| **1.5** | **抗幻觉的 Prompt 约束** | 同上："禁止编造数据，工具未返回的数据一律不得臆造" | Day 8 复盘：单轮对话时模型会凭训练知识编造"明天 3月15日"；接工具后用「禁止臆造 + 数据不足如实说明」约束 | ★★★★ |

### 模块 2 · Agent 编排（LangGraph）（6 个）

| 编号 | 知识点 | 代码位置 | 核心要点 | 新颖度 |
| --- | --- | --- | --- | --- |
| **2.1** | **LangGraph 状态机 vs 线性 Chain** | `agent.py:_build_graph` | Agent 需要「判断→调工具→再判断」的**循环**，线性 LCEL 表达不了；图能表达环、分支、回退，且可视化可测试 | ★★★★★ |
| **2.2** | **AgentState 与消息累加** | `AgentState` TypedDict | `messages: Annotated[list, add_messages]` 让消息在节点间自动合并去重，而不是覆盖 | ★★★★ |
| **2.3** | **ReAct 工具循环** | `agent ⇄ tools` 条件边 | `agent` 出 tool_calls → `tools` 执行 → 回流 `agent`，直到无 tool_calls 才 `END` | ★★★★★ |
| **2.4** | **条件边路由设计** | `_should_continue`、`_should_error` | 两条路由函数分别决定「是否进工具」和「是否进兜底」，把控制流显式化 | ★★★★ |
| **2.5** | **图内兜底节点** | `_handle_error` | LLM 调用失败不让异常穿透，改为路由到兜底节点返回友好话术 | ★★★★ |
| **2.6** | **惰性单例编译图** | `_get_agent` | 首次调用才构建（因为要先异步加载 MCP 工具），进程内复用编译结果 | ★★★ |

### 模块 3 · 意图识别（4 个）

| 编号 | 知识点 | 代码位置 | 核心要点 | 新颖度 |
| --- | --- | --- | --- | --- |
| **3.1** | **三级意图识别架构** | `_classify_intent` | 强关键词预判 → LLM 分类 → 弱关键词兜底，逐级降耗、逐级保底 | ★★★★★ |
| **3.2** | **强关键词预判的真实动机** | `_strong_keyword_intent` 注释 | HTTP 层曾稳定把意图判成 `other`（直接调 `chat()` 却正常）→ 根因是 LLM 分类输出不稳定；于是高置信词直接定意图，**顺带省一次 LLM 调用**（省 token + 降延迟） | ★★★★★ |
| **3.3** | **意图驱动的工具绑定** | `TOOL_INTENTS` | 只有 weather/travel/outfit/knowledge 才 `bind_tools`，闲聊类不绑 → 少注入工具 schema，省 token | ★★★★ |
| **3.4** | **关键词优先级设计** | `_NEWS_KEYWORDS` 优先判定 | "台风资讯"含"台风"（天气强词）会误判成 weather，故资讯词先判并归入 knowledge | ★★★★ |

### 模块 4 · MCP 工具协议层（8 个）

| 编号 | 知识点 | 代码位置 | 核心要点 | 新颖度 |
| --- | --- | --- | --- | --- |
| **4.1** | **MCP vs function calling** | 全模块 | function calling 是**模型能力**（输出结构化调用），MCP 是**工具接入协议**（如何连接/发现/描述工具）；前者决定"调哪个"，后者决定"有哪些" | ★★★★★ |
| **4.2** | **FastMCP 声明式注册** | `mcp_server/server.py` | `@mcp.tool()` + docstring 即工具 schema，Args 段落直接变成参数说明，Agent 自动读取 | ★★★★★ |
| **4.3** | **双传输模式** | `server.py:main` | `stdio`（本地，拉起子进程）/ `streamable-http`（上线，独立部署扩容），一个 `--transport` 切换 | ★★★★★ |
| **4.4** | **工具动态发现与缓存** | `mcp_client.py` | `MultiServerMCPClient` 拉取工具列表，进程内缓存，重启后自动重新发现——**增删工具 Agent 零改动** | ★★★★★ |
| **4.5** | **stdio 子进程的 Python 解释器陷阱** | `_build_connection` | 必须用 `sys.executable`（venv 的 Python），否则系统 Python 没装 `mcp` 包 → `ModuleNotFoundError` | ★★★★ |
| **4.6** | **工具层错误不穿透** | `handle_tool_errors=True` | 工具抛异常时返回错误文本给 LLM 阅读，而不是中断整条链路 | ★★★★ |
| **4.7** | **有状态工具为何不能走 MCP** | `local_tools.py` 模块注释 | MCP 跑在独立子进程，`contextvars` 跨不了进程 → 拿不到 `user_id`。故**无状态公共工具走 MCP，有用户态私有工具走本地** | ★★★★★ |
| **4.8** | **工具分层架构结论** | `_get_all_tools` | `[ *mcp_tools, *local_tools ]` 在 Agent 层合并绑定，既保留 MCP 可插拔，又正确支持多租户 | ★★★★★ |

### 模块 5 · RAG 检索增强（10 个）

| 编号 | 知识点 | 代码位置 | 核心要点 | 新颖度 |
| --- | --- | --- | --- | --- |
| **5.1** | **RAG 双阶段链路** | `rag_service.py` | 离线：文档 → 分块 → embedding → pgvector；在线：问题 → embedding → 余弦检索 → TopK 拼 Prompt | ★★★★ |
| **5.2** | **重叠分块策略** | `knowledge_loader.split_text` | chunk=300 / overlap=50；先按 `\n\n` 段落切（保语义），超长段落再滑窗硬切；重叠防语义在切点被截断 | ★★★★★ |
| **5.3** | **维度对齐的工程纪律** | `EMBED_DIM=1024` | 智谱 embedding-3 `dimensions=1024` 与 ORM `Vector(1024)` 强绑定，并在客户端**校验维度**，不符直接降级而非写库报错 | ★★★★ |
| **5.4** | **pgvector 余弦检索** | `rag_service.search` | `1 - (embedding <=> vec) AS similarity`，按距离升序取 TopK；原生 SQL 内联向量字面量以绕开 asyncpg 对 `::vector` 的命名参数误解析 | ★★★★ |
| **5.5** | **HNSW 近似最近邻索引** | `vector_cosine_ops` | 用 HNSW + 余弦算子做 ANN，数据量级不大时比引入 Milvus 更省运维 | ★★★★ |
| **5.6** | **RAG vs 微调的选型论证** | 面试宝典 Day 6 | RAG 知识可热更新、可溯源（能指出引用了哪段）、成本低；微调更新难、易遗忘旧知识 | ★★★★ |
| **5.7** | **多租户 RAG 的数据隔离** | `user_knowledge_service.search` | 每条分块记 `user_id`，检索 SQL 强制 `WHERE user_id = :uid`，**从查询层面**而非应用层隔离 | ★★★★★ |
| **5.8** | **Embedding 离线兜底（确定性伪向量）** | `embedding_client._local_pseudo_vector` | 无 Key / 调用失败时，3-gram hash 映射到 1024 槽位做词袋向量 + L2 归一化；**维度恒为 1024**，保证离线也能跑通全链路 | ★★★★★ |
| **5.9** | **公共库 / 私有库的架构分离** | `rag_service` vs `user_knowledge_service` | 共用分块器与 embedding 客户端，仅**存储表与检索范围**不同，避免重复实现 | ★★★★ |
| **5.10** | **RAG 升级方向（前瞻）** | 开发计划 Day 43 | 混合检索（pgvector 向量 + tsvector/BM25）+ Rerank 精排 + 评测集量化工信提升 | ★★★★★ |

### 模块 6 · Skill 能力封装（7 个）

| 编号 | 知识点 | 代码位置 | 核心要点 | 新颖度 |
| --- | --- | --- | --- | --- |
| **6.1** | **Agent Skills 三件套规范** | `skills/*/` | `SKILL.md`（说明书）+ `references/`（规则知识）+ `scripts/`（可执行逻辑），严格对齐 Anthropic Agent Skills 规范 | ★★★★★ |
| **6.2** | **frontmatter 驱动触发** | 各 `SKILL.md` 顶部 | 靠 `description` 让 AI 判断"何时该用这个能力"，而非硬编码触发条件 | ★★★★★ |
| **6.3** | **知识与逻辑分离** | `references/*.md` | 规则（温度档位、场景建议、评分权重）放 markdown：改规则不动代码，且**能被 RAG 索引复用** | ★★★★★ |
| **6.4** | **skill_loader 自动登记** | `skill_loader.py` | 正则解析 frontmatter，扫描 `skills/` 目录即自动发现，新增 Skill 无需改注册代码 | ★★★★ |
| **6.5** | **命名规范冲突的解法** | `travel_planning` vs `travel-planning` | 目录名用下划线（Python import 不支持连字符），frontmatter 内 `name` 用连字符（URL 友好，符合规范） | ★★★★ |
| **6.6** | **Skill 与 MCP 的分工** | 全模块 | Skill = 能力的知识与逻辑载体；MCP = 能力的调用出口。两者配合实现**能力层与调用层解耦** | ★★★★★ |
| **6.7** | **双出口设计** | `outfit_engine.run()` / `outfit_structured()` | 同一份逻辑两个出口：`run()` 返回文本材料给 LLM 生成人话；`_structured()` 返回 JSON 给前端直接渲染 | ★★★★★ |
| **6.8** | **规则的"不 break"细节** | `outfit_engine._build_rules` | 温度规则命中即 break（互斥档位），但天气规则**不 break**——"雷阵雨"要同时拿到防雷与防雨两条建议 | ★★★★ |

### 模块 7 · 工程化降级与上下文（6 个）

| 编号 | 知识点 | 代码位置 | 核心要点 | 新颖度 |
| --- | --- | --- | --- | --- |
| **7.1** | **四层 AI 降级体系** | 全局 | embedding 失败→伪向量；意图失败→关键词；生成失败→兜底节点；最外层 `chat()` catch 一切 → **接口永不 500** | ★★★★★ |
| **7.2** | **contextvars 请求级用户上下文** | `user_context.py` | 类 thread-local 但基于 asyncio 上下文，天然并发隔离；不改工具签名就能透传 `user_id`，Agent 层无感知 | ★★★★★ |
| **7.3** | **数据源可切换 + 自动降级** | `weather_service` / `web_search_service` | 和风 ↔ Open-Meteo、Tavily → DuckDuckGo，任一层故障不影响上层 | ★★★★ |
| **7.4** | **Celery + asyncpg 事件循环陷阱** | 工作日志 Day 4 | `asyncio.run()` 创建的 loop 关闭后连接失效（`NoneType has no attribute 'send'`）→ ①`NullPool` 独立引擎 ②模块级复用 loop | ★★★★★ |
| **7.5** | **RAG 建索引的异构引擎** | `rag_service._make_session` | Celery 任务用独立 NullPool 引擎，Web 请求复用主连接池，避免跨事件循环复用连接 | ★★★★ |
| **7.6** | **幂等 upsert 的 AI 侧应用** | `_store_chunks` | `on_conflict_do_update(index_elements=["source","chunk_index"])`，重复建索引不产生重复块 | ★★★★ |

### 模块 8 · 流式输出与多轮记忆（6 个）

| 编号 | 知识点 | 代码位置 | 核心要点 | 新颖度 |
| --- | --- | --- | --- | --- |
| **8.1** | **SSE 流式对话** | `routers/chat.py` | `sse-starlette` 的 `EventSourceResponse` + LangGraph `astream(stream_mode="messages")` 逐 token 推送 | ★★★★★ |
| **8.2** | **自定义事件协议** | 同上 | `{type:"intent"}` / `{type:"token"}` / `{type:"done"}`；意图先行推送，前端可先渲染标签再等正文 | ★★★★ |
| **8.3** | **过滤非生成节点的增量** | `meta.get("langgraph_node") != "agent"` | 意图识别节点也会产出消息，必须按节点名过滤，否则意图标签会混进答案流 | ★★★★★ |
| **8.4** | **前端手动解析 SSE** | `frontend-user/src/api/chat.ts` | axios 无法逐块读流，必须用原生 `fetch + ReadableStream + TextDecoder`；**代价是要手动带 `Authorization`**（曾漏掉 → 登录用户被当匿名，对话不落库） | ★★★★★ |
| **8.5** | **多轮上下文构造与截断** | `_build_initial_state` + `HISTORY_LIMIT=10` | 历史按 role 还原成 HumanMessage/AIMessage，只取最近 10 条防上下文爆炸；实测"省略主语仍能理解" | ★★★★★ |
| **8.6** | **会话分组与标题生成** | `list_conversations` | 取最近 500 条消息**在内存中按 conversation_id 分组**（避免复杂 SQL 聚合）；标题取该会话**最早一条用户提问**的前 40 字 | ★★★★ |

### 模块 9 · 搜索增强与内容处理（5 个）

| 编号 | 知识点 | 代码位置 | 核心要点 | 新颖度 |
| --- | --- | --- | --- | --- |
| **9.1** | **Tavily 作为 AI 场景搜索引擎** | `web_search_service._search_tavily` | 返回结构化结果 + 相关性 `score`，比通用搜索引擎更适合直接喂 LLM | ★★★★ |
| **9.2** | **平台抓取差异的实测结论** | `outfit_inspiration.py` 注释 | 抖音可被搜索引擎索引 → 拿具体内容；小红书对搜索引擎屏蔽 → **改提供搜索页直达链接**兜底 | ★★★★★ |
| **9.3** | **搜索词动态构造** | `_season_of` + `build_portals` | 按实时气温推导季节词，拼出"广州 秋季逛街穿搭"，让检索结果贴合当下 | ★★★★ |
| **9.4** | **网页正文提取（LLM 前置清洗）** | `article_extractor.py` | `HTMLParser` 优先只取 `<p>` 段落（自然滤掉导航/时间戳）；短于 250 字或命中页脚特征词则判为失败→降级原文链接 | ★★★★ |
| **9.5** | **多源资讯采集与去重** | `weather_news_service.py` | 中央气象台预警 + 中国天气网 + Tavily 三源合并，按标题去重后入库 | ★★★ |

---

## 三、博客选题规划（14 篇 · 按推荐顺序）

> 每篇对应一个可独立成篇、有代码有结论的选题。★ 为推荐优先级。

### 第一批：Agent 架构主线（差异化最强，建议先写）

| # | 拟定标题 | 覆盖知识点 | 核心看点 |
| --- | --- | --- | --- |
| 1 ★★ | **从 0 到 1 用 LangGraph 搭一个带工具调用的 Agent：状态、循环与兜底** | 2.1–2.6、1.3 | 完整图代码 + 为什么不用 if-else + 条件边路由 + 兜底节点 |
| 2 ★★ | **MCP 实战：把工具层从 Agent 里彻底解耦** | 4.1–4.8 | 双传输模式、动态发现、stdio 解释器坑、`handle_tool_errors` |
| 3 ★★ | **MCP 工具拿不到 user_id？用 contextvars 做请求级多租户隔离** | 4.7、7.2、5.7 | 全项目最有辨识度的一篇：进程隔离 vs 上下文隔离的架构取舍 |
| 4 ★ | **意图识别怎么做得又稳又省：三级降级架构** | 3.1–3.4 | 强词预判的真实动机（线上 intent=other bug 复盘）+ 省 token |
| 5 ★ | **Agent 永不 500：四层降级体系设计** | 7.1–7.5 | 每层降级的具体触发条件与兜底动作，可直接抄的容错范式 |

### 第二批：RAG 与检索（面试高频，需有数据）

| # | 拟定标题 | 覆盖知识点 | 核心看点 |
| --- | --- | --- | --- |
| 6 ★★ | **pgvector 实战：分块、1024 维对齐与余弦检索的工程细节** | 5.1–5.5 | overlap 为什么是 50、维度校验、asyncpg 的 `::vector` 坑 |
| 7 ★★ | **多租户 RAG：让每个用户只检索到自己的知识库** | 5.7、5.9、4.7 | 查询层强制过滤 + 公共库/私有库分离 + 与 MCP 的分层 |
| 8 ★ | **Embedding 挂了怎么办？用 n-gram hash 造一个确定性兜底向量** | 5.8 | 冷门但很实用：离线可联调、维度恒定、相同文本向量一致 |
| 9 ★ | **RAG vs 微调：一个出行助手项目的选型推演** | 5.6、5.10 | 加上混合检索 + Rerank + 评测集的前瞻设计 |

### 第三批：Skill 与提示工程（贴合最新规范）

| # | 拟定标题 | 覆盖知识点 | 核心看点 |
| --- | --- | --- | --- |
| 10 ★★ | **Anthropic Agent Skills 规范落地：把能力打包成文件夹** | 6.1–6.6 | SKILL.md/references/scripts 三件套 + 自动发现 + 与 MCP 分工 |
| 11 ★ | **一份逻辑两个出口：Skill 同时服务 LLM 与前端** | 6.7、6.8 | `run()` 给 LLM 材料、`_structured()` 给前端 JSON 的双入口设计 |
| 12 ★ | **提示词工程进阶：把决策规则写进 System Prompt** | 1.3、1.4、1.5 | 复合问题多工具协同、抗幻觉约束、反问/直答的边界 |

### 第四批：体验与数据侧（可作为系列补充）

| # | 拟定标题 | 覆盖知识点 | 核心看点 |
| --- | --- | --- | --- |
| 13 ★ | **SSE 流式对话全链路：从 LangGraph astream 到前端 ReadableStream** | 8.1–8.4 | 事件协议设计、节点过滤、axios 读不了流的坑 |
| 14 ★ | **多轮记忆与搜索增强：上下文截断、会话分组、网页正文提取** | 8.5–8.6、9.1–9.5 | 多轮上下文构造 + 平台抓取差异实测 + LLM 前置清洗 |

---

## 四、写作建议

**推荐开篇**：选题 **3（contextvars 多租户隔离）** 或 **2（MCP 实战）**。
理由：这两篇的知识密度最高、市面上同类文章少、面试可讲性强，且能自然带出整个 Agent 架构，适合作为系列第一篇建立技术标签。

**系列命名建议**：`AI Agent 工程化实战`（01 ~ 14），每篇结尾指向下一篇，形成体系感。

**每篇建议结构**：
1. 场景与问题（要解决什么真实痛点）
2. 方案设计与取舍（为什么这么选，否掉了什么）
3. 核心代码（带注释，可直接复用）
4. 踩坑记录（真实的报错与根因——这是最有价值的部分）
5. 结论与可复用要点

**素材来源**：`面试宝典.md`（逐日技术要点）、`工作日志.md`（踩坑与验证数据）、`Skill技术解析.md`（Skill 专题）——这三份文档已经沉淀了大部分"为什么"和"踩了什么坑"，可直接作为博客的一手素材。

---

## 五、可通过项目继续深挖的知识点（尚未落地，可做前瞻篇）

| 方向 | 开发计划位置 | 可写角度 |
| --- | --- | --- |
| 多智能体协作（Supervisor 架构） | Day 41 | 单 Agent → 领域 Agent + Supervisor 路由，附效果/延迟对比 |
| AI 一键排行程 Skill | Day 40 | 多工具编排链：查天气规避雨天 → 景点检索 → 路线耗时 → 生成行程 |
| RAG 混合检索 + Rerank | Day 43 | 向量召回 + BM25 双路合并 + 交叉编码器精排 + 评测集 |
| 用户画像与偏好学习 | Day 45 | 行为采集 + 衰减权重画像 + 推荐排序个性化 |
| 主动服务（AI + 推送） | Day 34–36 | 定时智能早报、预警实时推送、行程天气冲突提示 |
| 时序数据分析支撑决策 | Day 42 | TimescaleDB 连续聚合 + 同比环比，为 AI 提供趋势上下文 |
