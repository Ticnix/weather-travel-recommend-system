# 多租户 RAG：让每个用户只检索到自己的知识库

> 「AI Agent 工程化实战」系列 · 05
> 项目背景：广州气象大数据 + AI 智能体出行推荐系统（FastAPI + LangGraph + MCP + pgvector）
> 本文引用了 MCP 官方架构文档、PostgreSQL 官方文档、pgvector 官方 README 原文，链接见文末「参考资料」

---

## 0. 先用三句话讲清楚这篇在说什么

1. **要解决的问题**：上一篇的 RAG 是"全库检索"——所有用户查的是同一份公共知识库。但真实产品里用户会问"**我**上次收藏的那家餐厅叫什么"，这就需要一份**每个人自己的知识库**，而且**绝不能串号**——我看到别人的笔记，是事故。
2. **采用的方案**：把"谁在问"这件事**传到 SQL 里**——每条向量块都记 `user_id`，检索语句强制带 `WHERE user_id = :uid`。隔离做在**查询层**，不是应用层"记得加过滤"。
3. **它的边界**：这个 `uid` 只在 **Agent 进程内**有效。独立进程的 MCP 工具读不到它——这恰好解释了上一篇那个结论：**公共工具走 MCP，私有工具必须留在本地**。

如果你只想记一句话：

> **多租户隔离的底线是"隔离落在查询条件里"**——不是在代码注释里写"记得过滤 user_id"，而是让这条 SQL 不带上 `uid` 就跑不起来。

---

## 目录

1. 从"我上次收藏的餐厅"说起
2. 先讲清概念：多租户到底在防什么
3. 三种隔离方案，及为什么选了最"笨"的那个
4. 落地：一条链路上的四层身份传递
5. 数据怎么分家：公共库 vs 私有库
6. 公共工具走 MCP、私有工具留本地——架构上的必然
7. 边界与易错点
8. 小结与下一篇

---

## 一、从"我上次收藏的餐厅"说起

用户在对话框里输入：

> 我上次收藏的那家餐厅叫什么来着？

这句话和上一篇的"广州塔几点关灯"有本质区别：

| | 广州塔几点关灯 | 我上次收藏的餐厅 |
| --- | --- | --- |
| 数据范围 | **所有人共享** 的攻略知识 | **只有我能看** 的个人笔记 |
| 数据来源 | `knowledge_base/` 里 16 篇公共文档 | 用户自己上传的行程、攻略、笔记 |
| 关键问题 | "哪段内容和问题最相关" | "**这是谁**的内容"，然后才是"哪段相关" |

第二类问题多出来一个维度：**身份**。

而且这个身份维度不是"加分项"，是**红线**。假如隔离没做好：用户 A 问"我收藏的餐厅"，系统把用户 B 的私人笔记检索出来喂给模型——那就不是"回答不准"的问题了，是**数据泄露事故**。

所以这一篇不讲"怎么让检索更准"（那是上一篇的事），只讲一件事：**怎么保证每个人只看到自己的东西。**

---

## 二、先讲清概念：多租户到底在防什么

### 2.1 什么是"租户"

"租户"（tenant）这个词来自 SaaS 领域：**一套系统同时服务很多个客户，每个客户就是一个"租户"**。

这个项目里没有企业客户，租户就是**单个用户**。但性质是一样的：

```
一套代码 + 一个数据库
    ├─ 用户 A 的数据  ← 只有 A 能读
    ├─ 用户 B 的数据  ← 只有 B 能读
    └─ 用户 C 的数据  ← 只有 C 能读
```

**关键在"一套"两个字**。如果给每个用户单独部署一套系统，那叫"多实例"，不叫多租户，也没有隔离问题——但那显然不现实。

多租户的本质是：**在共享的基础设施上，用软件手段划出互不可见的边界。** 我们做的每件事（鉴权、字段标记、查询过滤），都是在**用代码模拟那个不存在的物理墙**。

### 2.2 三层隔离，缺一层就漏

这是这篇最核心的一张图。数据从用户输入到落进数据库，中间要穿过三层，**每一层都得有隔离机制**：

```mermaid
flowchart TB
    subgraph L1["第一层：身份层（你是谁）"]
        A1["HTTP 请求<br/>Authorization: Bearer &lt;jwt&gt;"]
        A2["JWT 解析 → user_id"]
        A1 --> A2
    end

    subgraph L2["第二层：传递层（身份怎么走）"]
        B1["Agent 进程内<br/>contextvars 透传"]
        B2["本地工具读到 user_id"]
        B1 --> B2
    end

    subgraph L3["第三层：存储层（数据怎么分）"]
        C1["私有表带 user_id 列"]
        C2["SQL 强制 WHERE user_id = :uid"]
        C1 --> C2
    end

    L1 --> L2 --> L3 --> D["只返回该用户的数据"]
```

三层各自防不同的漏洞：

| 层 | 防什么 | 项目里的实现 |
| --- | --- | --- |
| 身份层 | "未登录的人伪装成别人" | JWT 解码 + 查库确认用户存在 |
| 传递层 | "工具不知道怎么拿到身份" | `contextvars` 请求级透传 |
| 存储层 | "查询时忘了过滤" | SQL 里硬写 `WHERE user_id = :uid` |

**这张图也解释了为什么"只在最后写个 WHERE 就行"是危险的**——那你前面的两层的漏洞（伪造身份、身份丢失）直接就打穿了。隔离是**纵深防御**，不是一道墙。

---

## 三、三种隔离方案，及为什么选了最"笨"的那个

业界做多租户数据隔离，主流有三种做法。先把它们摆出来，再说这个项目为什么选了第三种。

### 方案 A：每个用户一个数据库（物理隔离）

```
user_1 → 数据库 db_1
user_2 → 数据库 db_2
user_3 → 数据库 db_3
```

**优点**：隔离最彻底，物理上就碰不到一起。
**缺点**：连接数爆炸、迁移要跑 N 遍、运维噩梦。这套只适合"客户是企业、数量在几十以内"的 SaaS。

**结论：用户级场景直接排除。**

### 方案 B：共享表 + 行级安全（RLS）

PostgreSQL 自带 **Row Level Security**：给表加一条策略，数据库**自动**帮你过滤行。比如：

```sql
ALTER TABLE user_knowledge ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_isolation ON user_knowledge
    USING (user_id = current_setting('app.current_user_id')::int);
```

之后你哪怕写一条裸的 `SELECT * FROM user_knowledge`，数据库也只会返回属于当前用户的行——**过滤是数据库强制的，代码忘了也拦得住**。

这是**很优雅**的方案，隔离强度最高。但它需要：每个请求进来先 `SET app.current_user_id`、连接池要小心"设置串号"、异步驱动和连接复用的配合要额外验证。

**结论：对当前阶段的收益/复杂度比不划算**，但它是一个明确的升级方向，值得记住。

### 方案 C：共享表 + 应用层显式过滤（项目采用的）

就是最简单粗暴的一种：**表里加一个 `user_id` 列，每条查询都自己带上 `WHERE user_id = :uid`。**

```sql
SELECT title, content, 1 - (embedding <=> '...'::vector) AS similarity
FROM user_knowledge
WHERE user_id = :user_id AND embedding IS NOT NULL      -- ← 这一行就是隔离
ORDER BY embedding <=> '...'::vector ASC
LIMIT :top_k
```

看着"最笨"，但对这个项目是最合适的：

- **和现有表结构零冲突**——公共知识库、用户、行程、反馈全在一个库，加列是最小改动；
- **不引入连接池管理的复杂度**——不需要处理"连接复用时 current_user_id 串号"的问题；
- **代价可控**——过滤写在 SQL 文本里，review 时**肉眼可查**，一眼就能看出哪条查询隔离了、哪条漏了。

**方案 C 的代价是"依赖自觉"**：一旦有人写新查询忘了带 `WHERE user_id`，就会漏数据。所以项目的做法是——**把 `user_id` 做成这个函数的必填参数**，让"忘记过滤"这件事在**调用时**就被挡住：

```python
async def search(
    user_id: int,              # ← 必填，没有默认值
    query: str,
    top_k: int = 5,
    db: AsyncSession | None = None,
) -> list[dict[str, Any]]:
```

注意 `user_id` 是**位置参数、无默认值**——你想调用它，就必须显式提供一个身份。**这比写一行注释"记得过滤"强得多：前者是类型系统帮你把关，后者是祈祷。**

---

## 四、落地：一条链路上的四层身份传递

现在把上面那张"三层隔离"图落到真实代码。`user_id` 从 HTTP 请求出发，要穿过四棒。

### 第一棒：HTTP 请求带 JWT

用户登录后拿到 token，之后的请求都在头里带着：

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 第二棒：鉴权依赖解析出用户对象

FastAPI 的依赖注入在这里很漂亮——`deps.py` 把"从 token 到用户"封装成一个**可复用的类型**：

```python
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """从 Bearer Token 解析用户，用户不存在则 401。"""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效或过期的身份凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exc
    except jwt.PyJWTError:
        # from None：切断异常链，对外只暴露「凭证无效」，
        # 不把 JWT 解析的内部报错细节泄漏给客户端
        raise credentials_exc from None

    user = await db.scalar(select(User).where(User.id == int(sub)))
    if user is None or not user.is_active:
        raise credentials_exc
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
```

有两个细节值得单独说：

**① 异常链被主动切断了。** `raise ... from None` 那行是在**主动隐藏内部细节**：如果 JWT 解析失败，默认的异常信息里可能带着库的内部堆栈或提示，直接抛给客户端是不合适的。`from None` 把它切断，对外只留一句"无效或过期的身份凭证"。**安全和排错的平衡点，通常就是"给外人看结论，给自己留日志"。**

**② `CurrentUser` 是一个"类型别名"。** 这样路由函数里只要写 `current: CurrentUser`，就自动获得了"必须是登录用户"的语义——**鉴权从"一段要记得调的代码"变成了"一个写在签名里的类型"。**

### 第三棒：路由层拿到 `current.id`

路由函数里，身份就变成了一行普通的参数：

```python
@router.post("/search", response_model=dict)
async def search_my_knowledge(
    payload: UserKnowledgeSearch,
    current: CurrentUser,                                     # ← 身份
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """在本人私有知识库中检索。"""
    items = await user_knowledge_service.search(
        user_id=current.id,                                   # ← 往下传
        query=payload.query,
        top_k=payload.top_k,
        db=db,
    )
    return success({"items": items, "total": len(items)}, message="检索完成")
```

注意这里有个**很关键的设计**：`user_id` 是**从 `current.id` 取的，不是从请求体里读的**。

这条细节看着小，但它是隔离的关键。如果身份从 `payload` 里读——比如请求体允许传 `user_id`——那用户只要改一下参数就能查别人的数据了。**身份必须来自凭证（服务端解析的 JWT），绝不能来自用户可控的输入（请求体、query 参数）。**

> 一句话记住：**凡是"你是谁"，必须服务端说了算；凡是"你想干什么"，才轮到客户端说。**

### 第四棒：SQL 里的 `WHERE`

到了服务层，身份落了地：

```python
stmt = text(
    f"""
    SELECT title, source, content, chunk_index, 1 - (embedding <=> '{vec_literal}'::vector) AS similarity
    FROM user_knowledge
    WHERE user_id = :user_id AND embedding IS NOT NULL
    ORDER BY embedding <=> '{vec_literal}'::vector ASC
    LIMIT :top_k
    """
)
result = await s.execute(stmt, {"user_id": user_id, "top_k": top_k})
```

**这一行 `WHERE user_id = :user_id`，就是整个多租户隔离的最后一道门。** 前面三层都是为它服务的——把"当前是谁"安全、无损地送到这里。

### 顺带一提：`user_id` 在枚举/删除里同样不能漏

隔离不只在检索里，列表和删除也一样：

```python
# 列表：按 user_id 分组统计
"SELECT title, source, COUNT(*) AS chunks, MAX(created_at) AS latest
 FROM user_knowledge
 WHERE user_id = :user_id
 GROUP BY title, source"

# 删除：只删自己的
stmt = delete(UserKnowledge).where(
    UserKnowledge.user_id == user_id, UserKnowledge.title == title
)
```

**删除那条尤其要小心**——如果没有 `UserKnowledge.user_id == user_id` 这个条件，用户传一个别人笔记的标题，就能把别人的数据删掉。这类漏洞比"看到别人的数据"更严重。

---

## 五、数据怎么分家：公共库 vs 私有库

身份这条线讲完了，接下来是"数据住哪"。项目里用了**两张表**：

| | 公共知识库 | 私有知识库 |
| --- | --- | --- |
| 表名 | `knowledge_chunks` | `user_knowledge` |
| 数据来源 | `knowledge_base/` 目录下 16 篇预置文档 | 用户自己上传的文本 |
| 有没有 `user_id` | **没有** | **有**（且建了索引） |
| 谁都能查吗 | 是，所有人共享 | 否，只能查自己的 |
| 唯一约束 | `(source, chunk_index)` | 无（同一标题可多版本） |
| 服务文件 | `rag_service.py` | `user_knowledge_service.py` |
| 工具出口 | MCP 工具 `search_knowledge` | 本地工具 `search_my_plans` |

私有表里那行 `user_id` 定义是这样的：

```python
user_id: Mapped[int] = mapped_column(
    ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
)
```

三个点：

- **`nullable=False`**——不允许出现"没有主人"的数据，从建表层面堵死匿名数据；
- **`index=True`**——`WHERE user_id = ...` 是最高频的查询条件，必须有索引，否则数据量一大就全表扫；
- **`ondelete="CASCADE"`**——用户注销时，他的私有知识自动级联删除。**这是合规要求，不是可选项**——用户要求删除账号，你不能把数据留在库里。

### 为什么要分成两张表，不在一张表里加个可空 `user_id`

这是个很自然的疑问："能不能一张表搞定，公共数据的 `user_id` 是 NULL，私有的填具体值？"

技术上能，但这个项目选择分表，理由是**"可空字段"会把隔离问题变成一道智力题**：

- 一旦 `user_id` 可空，每条查询的语义就变成了"`user_id IS NULL` 或 `user_id = :uid`"——**两个条件都写对才安全，漏一个就错**；
- 而分表之后，公共表的查询**天然不需要考虑身份**，私有表的查询**天然必须考虑身份**。**问题的复杂度被表的边界切开了。**

而且两张表还能各自优化——公共表可以靠 `(source, chunk_index)` 做幂等 upsert（上一篇讲的），私有表不需要（因为用户可能上传多份同名文档）。

> 一句话记住：**分表不是为了性能，是为了让"要不要过滤身份"这件事变成结构问题，而不是记忆问题。**

### 共用了什么

有意思的是，两张表虽然分开，**分块器和 embedding 客户端是完全共用的**：

```python
"""用户私有知识库服务（多租户 RAG）。

与公共知识库（rag_service）共用同一套分块器和 embedding 客户端，
仅存储表与检索范围不同（按 user_id 隔离）。
"""
```

私有库上传时调用的是同一个分块函数：

```python
chunks = split_text(content, 300, 50)          # 和公共库同一套参数
vectors = await embedding_client.embed_texts(chunks)   # 同一个 embedding 客户端
```

**复用"怎么切、怎么算向量"，只在"存哪、查多少"上分家。** 这个划分很干净——分块和向量化是**纯技术问题**，两张表没有差异；而存储和范围是**业务问题**，必须分开。

---

## 六、公共工具走 MCP、私有工具留本地——架构上的必然

这是本篇和系列前两篇的交汇点，也是我最想讲清楚的一段。

### 6.1 问题的由来

系列第 2 篇讲了：项目把工具层拆成了 MCP 工具（独立进程）+ 本地工具（Agent 进程内）。当时给出的理由是"有状态工具不能走 MCP"。

现在我们知道得更精确了：**"有状态"这个词太模糊，真正的约束是"身份拿不到"。**

MCP 官方架构文档里有一句关键表述（参考资料 1）：

> *"MCP is a stateless protocol."*

以及关于 transport 的说明：stdio 传输下，**server 通常只服务单个 client**。这意味着：**MCP Server 是一个独立的进程，它和 Agent 进程之间只有"工具调用"这条协议通道，没有共享内存、没有共享上下文。**

而 `user_id` 是怎么传的？`contextvars`——**进程内的**上下文变量。它**跨不了进程边界**（上一篇详细论证过）。

所以：

```
Agent 进程 ─── contextvars 里的 user_id ──── 本地工具 ✅ 读得到
    │
    └─ MCP 协议 ──── 独立子进程 ──── 空上下文 ── MCP 工具 ❌ 读不到
```

**这就是"私有工具必须留在本地"的根本原因**——不是设计偏好，是进程边界决定的。

### 6.2 于是工具有了清晰的分工

| | MCP 工具（7 个） | 本地工具（2 个） |
| --- | --- | --- |
| 运行位置 | 独立进程（stdio / http） | Agent 进程内 |
| 需要的身份 | **不需要** | **需要** |
| 工具清单 | `get_weather` `get_forecast` `search_news` `search_knowledge` `web_search` `plan_travel_route` `recommend_outfit` | `search_my_plans` `check_itinerary_weather` |
| 能否被复用 | 可以，任何 client 都能接 | 只有本 Agent 能用 |
| 数据范围 | 公共数据 | 用户私有数据 |

注意一个**看起来矛盾、其实合理**的地方：MCP 里也有 `search_knowledge`（知识检索），本地里也有 `search_my_plans`（也是知识检索）。**两个都是"检索知识"，区别只有一个：要不要 `user_id`。**

- `search_knowledge` 查的是公共库，谁问结果都一样 → 无状态 → 可以走 MCP，好处是可插拔、可复用；
- `search_my_plans` 查的是私有库，必须知道"谁在问" → 有状态 → 必须留本地。

**工具的归属不是按"功能"分的，是按"是否需要身份"分的。** 这个判断标准非常清晰，新加工具时只要问一句"它需要知道用户是谁吗"，归属就定了。

### 6.3 本地工具怎么把身份读出来

本地工具里那句读取，就是整条链路的终点：

```python
@tool
async def search_my_plans(query: str, top_k: int = 5) -> str:
    """在当前登录用户自己的私有知识库（上传的出行计划/旅游攻略/笔记）中检索。

    仅检索当前用户本人上传的内容，与其他用户隔离。
    """
    user_id = get_current_user_id()                       # ← 从上下文取
    if user_id is None:
        return "当前未登录，无法检索个人知识库。请先登录后重试。"   # ← 匿名兜底

    items = await user_knowledge_service.search(user_id, query.strip(), top_k)
    ...
```

两个细节：

**① 工具的签名里没有 `user_id`。** 这是 `contextvars` 方案最大的好处——**工具对"怎么拿到用户"这件事完全无感知**，它只是调用一个函数。如果改用"显式传参"，那每个工具签名都要加 `user_id`，而且**模型能看到这个参数、可能会去填它**（这就危险了）。

**② 未登录时返回的是话术，不是异常。** `if user_id is None: return "当前未登录..."` ——这条错误文本会作为**工具结果回给 LLM**，模型据此就能回复用户"请先登录"。这是系列第 1 篇讲的"工具层错误降级"在业务上的应用：**别让异常穿透，把异常翻译成模型能读懂的话。**

### 6.4 最后在 Agent 层合并

两类工具最终在 Agent 节点合并绑定：

```python
async def _get_all_tools() -> list:
    """合并 MCP 工具（无状态公共工具）+ 本地工具（有用户态私有工具）。"""
    mcp_tools = await get_mcp_tools()
    local_tools = get_local_tools()
    return [*mcp_tools, *local_tools]
```

**对模型来说，这 9 个工具是一视同仁的**——它不知道哪个跑在子进程、哪个在本地，只知道每个工具叫什么、能干什么。**复杂性被"工具层"吸收了，模型层保持干净。**

```mermaid
flowchart LR
    U["用户提问<br/>我上次收藏的餐厅"] --> AG["Agent 节点<br/>bind_tools(9 个)"]
    AG --> M{"模型决策"}
    M -->|"需要身份"| LT["本地工具<br/>search_my_plans"]
    M -->|"公共数据"| MT["MCP 工具<br/>search_knowledge"]
    LT --> CV["contextvars<br/>user_id"] --> DB1[("user_knowledge<br/>WHERE user_id")]
    MT --> PROC["独立子进程<br/>无身份"] --> DB2[("knowledge_chunks<br/>全量检索")]
```

---

## 七、边界与易错点

### 7.1 三个必须避开的坑

**坑一：身份从请求体里读。**

```python
# ❌ 危险：用户能自己填 user_id
async def search(payload: UserKnowledgeSearch, ...):
    items = await service.search(payload.user_id, payload.query)   # 越权！
```

**正确做法**：身份只能来自服务端解析的凭证（`current.id`）。输入参数里**永远不该出现 `user_id`**。

**坑二：把 isolation 写成"记得加"。**

隔离如果只存在于人的记忆里，早晚会漏。项目用的对策是**把 `user_id` 做成必填参数**——漏了就报错，而不是静默返回别人的数据。更好的做法是方案 B（RLS），让数据库兜底。

**坑三：删改接口忘了带条件。**

```python
# ❌ 只按 title 删 → 能删别人的
delete(UserKnowledge).where(UserKnowledge.title == title)

# ✅ 带上 user_id
delete(UserKnowledge).where(
    UserKnowledge.user_id == user_id, UserKnowledge.title == title
)
```

检索漏了是"看到别人的数据"，删改漏了是"改坏别人的数据"——**后者更不可逆**。review 时优先盯这两类。

### 7.2 一个值得留意的细节

`list_documents` 和 `delete_document` 都是按 **`title`** 定位的（不是 `id`）：

```python
async def delete_document(user_id: int, title: str, ...) -> int:
    stmt = delete(UserKnowledge).where(
        UserKnowledge.user_id == user_id, UserKnowledge.title == title
    )
```

因为一个标题对应多个分块（一篇文档切了 N 块），按标题删正好一次删干净。但这也意味着：**如果用户上传了两份同名文档，删除会一起删掉。** 对"个人笔记"这个场景可以接受（同名通常就是同一份），但如果以后要支持版本管理，就该改成按 `id` 或加"文档 id"概念了。先记在这。

### 7.3 和方案 B（RLS）的距离

回头看，方案 C 的隔离强度**依赖应用层不出错**。要升级到方案 B，大致是这几步：

1. 私有表 `ENABLE ROW LEVEL SECURITY` 并建策略；
2. 请求进入时在会话上 `SET LOCAL app.current_user_id = :uid`（`LOCAL` 保证事务结束即失效，避免连接池串号）；
3. 保留应用层的 `WHERE`——**纵深防御，别急着删**。

这条路已经写进项目的升级方向里了。**关键是先意识到"方案 C 的自觉性是有风险的"，而不是等到出事才补。**

---

## 八、小结与下一篇

### 可复用清单

- **身份只从凭证来**：`user_id` 必须取自服务端解析的 JWT（`current.id`），**绝不能**从请求体/query 参数里读。
- **隔离落在查询条件里**：每条涉及私有数据的 SQL 都要带 `WHERE user_id = :uid`，包括**列表和删改**。
- **让"漏过滤"编译不过**：把 `user_id` 做成函数必填参数（无默认值），比写注释可靠。
- **建表三件套**：`nullable=False` + `index=True` + `ondelete="CASCADE"`。
- **分表而非可空字段**：让"要不要过滤身份"变成结构问题，不是记忆问题。
- **工具归属按"是否需要身份"分**：需要身份 → 留本地（`contextvars`）；不需要 → 可走 MCP（可插拔）。
- **工具签名里不放身份**：靠 `get_current_user_id()` 读，模型看不到、也填不了这个参数。
- **未登录返回话术**，把异常翻译成模型能读懂的一句"请先登录"。
- **纵深防御**：身份层（JWT）+ 传递层（contextvars）+ 存储层（WHERE），缺一层就漏。
- **升级方向**：PostgreSQL RLS 把过滤从"应用层自觉"下沉到"数据库强制"。

### 代码位置

`backend/app/core/deps.py`（JWT → `CurrentUser` / `OptionalUser`）、`backend/app/routers/user_knowledge.py`（路由层取 `current.id`）、`backend/app/services/user_knowledge_service.py`（SQL `WHERE user_id`）、`backend/app/models/user_knowledge.py`（表结构与索引）、`backend/app/services/local_tools.py`（`search_my_plans` 读上下文）、`backend/app/services/user_context.py`（`contextvars` 本体）、`backend/app/services/agent.py:_get_all_tools`（两类工具合并）。

### 下一篇预告

到这里，"能让 Agent 干活"这件事基本齐了——图、工具、上下文、检索都通了。但你可能发现一件事：**我几乎没讲"提示词"**。而实际上，这个项目的 Agent 里**几乎没有 if-else 编排流程**——决定"调哪个工具、什么顺序、什么时候该反问、什么时候直接答"的，全是写进 System Prompt 的那套规则。下一篇进**提示词工程**：怎么把决策规则写进系统提示词、复合问题怎么协同多个工具、以及"禁止编造"这类抗幻觉约束是怎么落地的。

---

## 参考资料

1. MCP 官方文档 · [Architecture overview](https://modelcontextprotocol.io/docs/learn/architecture)（"MCP is a stateless protocol."；hosts / clients / servers 与 transports 定义）
2. MCP 官方文档 · [Understanding MCP servers / Transports](https://modelcontextprotocol.io/docs/concepts/transports)（stdio 与 Streamable HTTP 的适用场景）
3. PostgreSQL 官方文档 · [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)（RLS 与 `CREATE POLICY` 语法，方案 B 的依据）
4. PostgreSQL 官方文档 · [Foreign Keys / `ON DELETE` 动作](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-FK)（`CASCADE` 语义）
5. FastAPI 官方文档 · [Dependencies / Security](https://fastapi.tiangolo.com/tutorial/security/)（依赖注入做鉴权的官方范式，`CurrentUser` 别名的来源）
6. pgvector 官方文档 · [README（Indexing / Filtering）](https://github.com/pgvector/pgvector)（带 `WHERE` 过滤条件的向量检索与索引的配合）
7. OWASP · [Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)（"不要信任客户端传来的身份"的权威依据）
