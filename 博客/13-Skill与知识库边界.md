# 我调了三个月 overlap=50，它其实一次都没生效

> Skill、知识文档、工具——AI Agent 项目里"知识"该怎么分家，以及我在切块器里实测出的一个静默失效参数。

> 「AI Agent 工程化实战」系列 · 13
> 项目源码：**[Ticnix/weather-travel-recommend-system](https://github.com/Ticnix/weather-travel-recommend-system)**
> 基于气象大数据的出行推荐系统，AI Agent 全栈项目。FastAPI + PostgreSQL(TimescaleDB/pgvector/PostGIS) + Redis；
> LangGraph + MCP + Skill + RAG，对接 DeepSeek API；React/Vue 前后端分离，实现 3D 天气可视化、智能出行穿搭推荐。
> （项目仍在更新中）

---

## TL;DR

1. **同一个需求有三种正确写法，选错了不会报错**：一条"雨天不排户外"的规则，可以写成工具、写成 Skill、写成知识文档。三者都能跑通，但后续维护成本差一个量级。
2. **切块器的 `overlap` 参数在这个项目里是静默失效的**。我用唯一锚点做了决定性实验：`overlap=0` 和 `overlap=50` 的输出**逐字节相同**，相邻块之间零重叠。参数被读进来了，也传下去了，就是没生效。
3. **`config.py` 里 `EMBED_CHUNK_OVERLAP = 50` 配了、`knowledge_loader.split_text()` 也接了、16 个文档也照切了**——这条链路上每一环看起来都对，所以没人会发现。
4. 顺带说清一件事：**16 个文档切成 33 块，全自研，不用 LangChain 的 splitter**，为什么。

---

## 目录

- [一、先看那个不报错的 bug](#一先看那个不报错的-bug)
- [二、概念先行：知识有三种落法](#二概念先行知识有三种落法)
- [三、这个项目的四条 Skill 长什么样](#三这个项目的四条-skill-长什么样)
- [四、知识库：16 个文档怎么变成 33 个向量](#四知识库16-个文档怎么变成-33-个向量)
- [五、回归正题：overlap 为什么没生效](#五回归正题overlap-为什么没生效)
- [六、可复用清单](#六可复用清单)
- [七、小结与下一篇](#七小结与下一篇)

---

## 一、先看那个不报错的 bug

我在核对项目知识库时随手跑了个实验：把 `EMBED_CHUNK_OVERLAP` 从 50 改成 0，看输出块会不会变。

```python
from app.services.knowledge_loader import split_text

text = "\n\n".join(f"锚点{i:02d}号：" + f"内容{i:02d}" * 25 for i in range(1, 13))

p0  = split_text(text, 300, 0)
p50 = split_text(text, 300, 50)

print(p0 == p50)   # True
```

**`True`。** 两块内容逐字节相同。

不放心，我又把每块里出现的"锚点"打印出来（每个锚点全文档唯一，只出现一次）：

```
===== overlap=0 -> 块数=6 =====
  #0 len=214 含锚点=['锚点01号', '锚点02号']
  #1 len=214 含锚点=['锚点03号', '锚点04号']
  #2 len=214 含锚点=['锚点05号', '锚点06号']
  ...
===== overlap=50 -> 块数=6 =====
  #0 len=214 含锚点=['锚点01号', '锚点02号']
  #1 len=214 含锚点=['锚点03号', '锚点04号']
  ...
  块#0 锚点=[1,2] -> 块#1 锚点=[3,4]   边界重叠的锚点=[]
  块#1 锚点=[3,4] -> 块#2 锚点=[5,6]   边界重叠的锚点=[]
```

块长一模一样，锚点严格瓜分，**边界重叠恒为 0**。

换个说法：`overlap` 这个参数，从配置文件到函数签名到调用链，全都写得好好的，但它**一次都没生效过**。

而这正是最危险的一类 bug——它不抛异常、不写日志、单测也能全绿（因为没人断言过"相邻块必须共享 50 个字"），而它对检索质量的影响是**隐性的**：一个横跨块边界的句子，被切成两半，两半各自都不完整，向量语义两头不到岸。

先把结论放这儿，第五节拆原因。这一节想说的是方法论：**配置项写对不等于逻辑生效**。凡是"声明了却没被验证"的参数，都应该假定它是坏的，直到你亲眼看见它起作用。

---

## 二、概念先行：知识有三种落法

回到正题。这个项目里 Agent 要"知道"很多东西，但**同样的知识，写在哪里是有讲究的**。我把它们分成三类：

| | 工具（Tool） | Skill | 知识文档（Knowledge） |
|---|---|---|---|
| 本质 | 一段**可执行代码** | 一套**流程说明 + 规则表 + 脚本** | 一段**自然语言文本** |
| 存放 | `mcp_server/tools.py`、`local_tools.py` | `backend/skills/<name>/` | `backend/knowledge_base/*.md` |
| Agent 怎么拿到 | Function Calling，模型选它、传参、拿返回值 | 加载全文进上下文，或按其流程调脚本 | 向量检索，只把**最相关的几块**塞进上下文 |
| 适合什么 | 需要**实时/精确数据**（天气、路线、地图 POI） | 需要**多步流程 + 固定规则**（排行程、评分） | 需要**背景叙述**（广州怎么玩、四季穿什么） |
| 改它的成本 | 要改代码、跑测试、发版 | 改 markdown 即可 | 改 markdown + 重建索引 |
| 出错的表现 | 报错、超时、返回空 | 流程走歪 | 检索到不相关内容 |

一句话概括三者的边界：

> **能算的写工具，有流程的写 Skill，只能读的写文档。**

举本项目里一个真实例子，同一句需求——"雨天不要安排户外活动"：

- **写成工具**：`plan_trip(query)` 内部调天气 API，判断降水，再决定排不排户外。✅ 这个项目就是这么做的。
- **写成 Skill 规则表**：在 `references/scoring-rules.md` 里写"降水 > X mm 则户外活动扣分"。✅ 出行规划 Skill 也这么做了，「天气分」占 0.3 权重。
- **写成知识文档**：在 `weather_travel_planning.md` 里写一段"高温天气出行建议"。✅ 也在，但**它只是背景，不保证被遵守**。

三种都写了，但**职责完全不同**：工具负责"实际不排"，Skill 负责"怎么打分"，文档负责"给人解释为什么"。把这三件事混在一个地方，就是后面维护的地狱。

---

## 三、这个项目的四条 Skill 长什么样

项目 `backend/skills/` 下是**标准的 Anthropic Agent Skills 结构**，四条：

```
backend/skills/
├── itinerary_planner/     # AI 一键排行程
│   ├── SKILL.md
│   └── scripts/planner.py          (32.7 KB —— 四者里逻辑最重)
├── itinerary_reminder/    # 行程天气提醒
│   ├── SKILL.md
│   ├── references/reminder-guide.md
│   └── scripts/reminder.py         (4.6 KB)
├── outfit_recommend/      # 穿搭推荐
│   ├── SKILL.md
│   ├── references/{temp,weather,scene,preference}-rules.md
│   └── scripts/outfit_engine.py    (7.1 KB)
└── travel_planning/       # 出行路线规划
    ├── SKILL.md
    ├── references/scoring-rules.md
    └── scripts/route_planner.py    (6.0 KB)
```

注意这个结构的分工，很有意思：

- **`SKILL.md`** 很短。`outfit_recommend` 的全文只有 **1263 字节**——它不含任何具体规则，只有「何时使用」「工作流程」「规则维度（一张汇总表）」「数据来源」。
- **`references/`** 才是规则本体。穿搭那条 Skill 把规则拆成了四张表：温度档位（4 档）、天气类型（6 类）、活动场景（10 种）、用户偏好（7 种）。
- **`scripts/`** 是可执行的那半。规则表是给**人和模型看的**，脚本是**真的会被调用的**。

看 `outfit_recommend/SKILL.md` 全文（去掉 frontmatter）：

```markdown
# 穿搭推荐 Skill

## 何时使用
- 用户问"明天穿什么""爬山穿什么""下雨天怎么穿""我怕冷穿什么"等穿搭问题。

## 工作流程
1. 获取气象参数（温度、天气现象、降水、风力）
2. 按「温度档位 + 天气类型 + 活动场景」匹配穿搭规则
3. 应用用户偏好调整
4. RAG 检索穿搭知识库增强上下文
5. 生成自然语言穿搭建议（上衣/下装/鞋/配饰 + 理由）

## 规则维度
| 维度 | 档位/类型 |
|------|----------|
| 温度 | 炎热≥30 / 温暖22~30 / 凉爽15~22 / 寒冷<15 |
| 天气 | 雨 / 雪 / 雷 / 风 / 雾 / 霾 |
| 场景 | 爬山/逛街/夜游/商务/通勤/露营/骑行/观景/亲子/摄影 |
| 偏好 | 怕冷/怕热/正式/运动/休闲/简约/时尚 |

详见 references/ 下各规则文档。

## 数据来源
- 天气：统一天气服务层
- 知识：RAG 知识库（weather_outfit_matching / outfit_advice 等文档）
```

**为什么 SKILL.md 要短**？这背后是 Anthropic 在 Agent Skills 规范里强调的**渐进式披露（progressive disclosure）**：模型先只看得到 `name` + `description`（几十字），判断"要不要用这个技能"；确定用了才加载 SKILL.md 全文；需要细则时再去读 `references/`。

这跟人查手册一样：先看目录，再翻章，最后才读那一页。**如果把 5 万字的规则表全塞进 SKILL.md，那每次对话都在为一个可能用不上的技能烧上下文**。

`outfit_recommend` 的设计正好卡在这个分界上：`SKILL.md` 1263 字节（进上下文不心疼），4 张规则表放 `references/`（按需读），真正的计算放 `scripts/outfit_engine.py`（压根不进上下文，直接执行）。

### 一个值得单独说的细节

`itinerary_planner/SKILL.md` 里有一段「关键设计」，我认为是全项目最值钱的一段设计说明：

```markdown
## 关键设计
- **不把「模型会听话」当作正确性依赖**：提示词里写"雨天不要排户外"只是建议，
  所以在生成之后做一次审计，把坏天气日的户外项换成室内候选。
  「雨天不排户外」因此从"希望如此"变成"返回结果里不可能出现"。
- **审计逻辑是纯函数**：LLM 输出不稳定，指望它对断言等于自找 flaky；
  把可验证的约束抽成纯函数（`needs_indoor` / `is_outdoor` / `audit_plan`），
  LLM 只负责创意部分，两者都能各测各的。
```

**"从'希望如此'变成'返回结果里不可能出现'"** —— 这句话值得抄下来贴墙上。

它的做法是：LLM 生成行程 → 逐条审计 → 坏天气日的户外项**强制替换**为室内候选。LLM 只负责"排得好看"，"排得对不对"交给纯函数判断。纯函数可以被穷举测试，LLM 不行。

这也解释了第 10 篇里那条测试原则（**断言编排，不断言模型输出**）：能变成纯函数的部分，就把它抽出来——抽出来的那一刻，它就从"靠祈祷"变成了"靠测试"。

---

## 四、知识库：16 个文档怎么变成 33 个向量

`backend/knowledge_base/` 下 16 个 Markdown，全部是公共知识（广州攻略 + 气象常识 + 穿搭对照）。我实测跑了一遍加载器：

```
docs_dir=knowledge_base  chunk_size=300  overlap=50
total_chunks=33
documents=16
chunk_len  min=76  max=299  avg=213
```

16 个文档 → 33 块，平均 213 字，最长 299（正好卡在 `chunk_size=300` 下方）。逐文档看：

```
guangzhou_climate.md         2 块    广州气候特点与最佳出行季节
guangzhou_food.md            2 块    广州地道美食指南
guangzhou_transport.md       2 块    广州交通出行指南
outfit_advice.md             2 块    广州旅行穿搭建议
weather_codes.md             3 块    气象常识：天气符号与 WMO 编码对照
...（共 16 个，合计 33 块）
```

### 为什么不用 LangChain 的 splitter？

因为切块策略**跟业务强绑定**。`knowledge_loader.py` 的 docstring 说得很清楚：

```python
"""知识库文档加载与重叠分块器。

职责：
- 扫描 knowledge_base 目录下的 .md/.txt 文档
- 按标题切分文档为章节，再按目标字符数 + 重叠进行分块
- 返回统一的 TextChunk 结构，供 embedding 入库使用
"""
```

它的切法是**段落优先**：先按 `\n\n` 拆段，能塞进就塞，塞不下就 flush，超长段落才滑窗硬切。

```python
    # 先按空行分段，尽量保证语义完整
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
                current = current[-overlap:] if overlap > 0 else ""  # 保留重叠
            # 处理超长段落：滑窗硬切
            if len(para) > chunk_size:
                i = 0
                while i < len(para):
                    end = min(i + chunk_size, len(para))
                    chunks.append(para[i:end].strip())
                    i = end - overlap if end < len(para) else len(para)
            else:
                current = para
```

这段代码的意图是好的：**尽量在语义边界（空行）切**，而不是机械地每 300 字一刀。因为中文段落的语义单元本来就是"段"，在段落中间切断，两个半块都语义残缺。

至于为什么自研 —— 本项目的文档形态极其单一（16 个纯 Markdown 的攻略/常识），用通用 splitter 反而要么依赖一个几百 KB 的库，要么要写一堆参数覆盖它的默认行为。**在形态统一时，50 行自研比引一个框架更可控**。

但恰恰是这 50 行，藏了第五节这个问题。

---

## 五、回归正题：overlap 为什么没生效

现在拆原因。关键就三行：

```python
if current:
    chunks.append(current)
    current = current[-overlap:] if overlap > 0 else ""   # ← ① 这里保留了尾部 50 字
...
else:
    current = para                                        # ← ② 这里把 current 整个覆盖掉了
```

执行顺序是这样的：

1. 块满了 → `chunks.append(current)`，然后 `current = current[-50:]`（保留尾部 50 字作为重叠）✅
2. 接着看当前段落 `para` 是否需要硬切：
   - 若 `len(para) > chunk_size` → 走滑窗分支，`current` 不被碰，重叠**保住了**
   - 若 `len(para) <= chunk_size` → 走 `else: current = para`，**第 ① 步刚保留的 50 字被直接覆盖** ❌
3. 下一轮循环进来，`current` 又变成 `current + "\n\n" + para`，继续累积

也就是说：**重叠只在一个狭窄的条件下（新段落本身就超长）能存活**。而在正常文档里，段落几乎都短于 300 字——也就是几乎永远走 `else` 分支——所以重叠**几乎永远被冲掉**。

这就是为什么我实测的 16 个真实文档，相邻块共用片段长度全是 **0**。

再看那个数字，`overlap` 在滑窗分支里也不对劲：

```python
i = end - overlap if end < len(para) else len(para)
```

窗口推进步长是 `chunk_size - overlap = 250`。这对"硬切长段落"是有效的重叠，但对"段落合并"路径完全没有帮助。

### 为什么这么久没被发现

因为**没有任何一处断言过它**。

- 写代码的人：读了 docstring"相邻块之间保留 overlap 字符"，看着第 ① 行 `current[-overlap:]`，觉得对。
- 改配置的人：`EMBED_CHUNK_OVERLAP = 50` 在那儿摆着，是个正经数字，没人怀疑。
- 跑测试的人（包括第 10 篇里那 81 个用例）：**一个都没覆盖 `split_text`**。
- 线上表现：检索照样能返回东西，只是跨边界的句子会漏——而"漏"这件事没人能一眼看出来。

这是一个典型的**静默失效**：链路每一环都"看起来对"，错误只出现在最后一公里的效果上，而效果没有度量。

### 怎么修

两种思路。**最省事的**：把重叠逻辑挪到"真正拼接下一块"的地方，而不是在 flush 时写一次就被覆盖。**更稳的**：承认段落优先策略下，重叠的价值本来就有限，索性显式表达意图。

我倾向于第二种——因为在段落优先切块里，**"不切断段落"已经承担了大部分防断裂职责**，重叠是第二道保险。与其留一个永远不生效的第二道保险，不如：

1. 要么**做成真的**：flush 时保留尾部重叠，且下一个块拼接时不清空它；
2. 要么**删掉参数**：配置里不要留 `EMBED_CHUNK_OVERLAP`，让"段落优先"成为唯一且明确的策略。

**留一个假装生效的参数，比没有这个参数更糟**——它会让人以为语义边界已经被保护了。

> 顺便，两个更通用的观察：
> - 这类 bug 的检测方式极其便宜：**改一个参数，看输出变不变**。变不变都只需要一次运行。我这次就是随手一试。
> - 凡是"声明了但没人验证"的东西，都应该被当成坏的。`overlap` 不是孤例——你们的代码里大概率也有几个。找它们的办法就是**把它调到 0，看结果动不动**。

### 检索质量本身是好的

需要说清楚：这个问题**不影响检索能返回结果**。我用真实 API 向量（`embedding.available = True`，1024 维）跑了几个查询：

```
Q: 广州哪里有好吃的早茶
   0.3672  [guangzhou_food.md#0]  '# 广州地道美食指南\n\n## 广式早茶\n广式早茶是广州饮食文化...'
   0.3135  [guangzhou_history_culture.md#1]  '## 骑楼建筑...'
   0.3074  [guangzhou_food.md#1]  '## 烧腊...'

Q: 明天爬白云山穿什么
   0.3630  [outfit_advice.md#0]              '# 广州旅行穿搭建议\n\n## 夏季穿搭...'
   0.3422  [weather_outfit_matching.md#0]    '# 天气与穿衣搭配对照建议\n\n## 炎热晴天（30℃以上）...'
   0.3390  [outfit_advice.md#1]              '## 冬季穿搭...'

Q: 从广州塔怎么去珠江新城
   0.3688  [guangzhou_shopping.md#1]         '## 珠江新城...'
   0.3582  [guangzhou_landmarks.md#0]        '# 广州必游景点推荐\n\n## 广州塔（小蛮腰）...'
```

Top-1 全中：早茶 → 美食指南，穿搭 → 穿搭建议，广州塔/珠江新城 → 对应景点。**分块策略是对的，检索是有效的，overlap 只是"本该有的第二道保险没装上"。**

我也顺手查了全库 33 块之间的近重复（相似度 ≥ 0.9 的块对）：**0 对**。这说明 16 个文档之间内容冗余度很低，没有互相污染——这对检索质量是好事。

---

## 六、可复用清单

1. **知识三分类的口诀：能算的写工具，有流程的写 Skill，只能读的写文档。** 拿不准时问自己："这条知识变了，我要改代码吗？"要 → 工具；不用 → 文档。
2. **SKILL.md 要短，规则表放 `references/`。** 渐进式披露的前提是"目录要薄"。本项目最薄的 SKILL.md 只有 1263 字节。
3. **不把"模型会听话"当作正确性依赖。** 提示词里的约束只是建议；要变成保证，就在生成之后加一道**纯函数审计**。
4. **能抽成纯函数的逻辑就抽出来。** 抽出来的那一刻，它从"靠祈祷"变成"靠测试"。
5. **配置项写对 ≠ 逻辑生效。** 验证方法：把它改成 0，看输出变不变。变了说明生效，不变说明它是装饰品。
6. **静默失效最难发现，因为它没有症状。** 一份"参数名 + 期望行为"的断言表，比多写十个 happy-path 测试更能救命。
7. **自研切块器的合理前提是形态统一。** 文档全是同构 Markdown 时，50 行自研比引框架可控；一旦格式花样变多，就该换成成熟的 splitter。

---

## 七、小结与下一篇

这一篇的主线是"知识怎么分家"：

- **工具 / Skill / 知识文档**，三种落法职责不同，混在一起就是维护地狱；
- **Skill 三段式**（SKILL.md + references/ + scripts/）是渐进式披露的物理载体，短的那个才是入口；
- **知识库 16 文档 → 33 块**，段落优先切块，全自研；
- 以及一个我实测出来的**静默失效 bug**：`overlap` 参数在这个项目里从未生效，`overlap=0` 与 `overlap=50` 输出逐字节相同。

最后一句总结我认为最值得记住的：**"配置里写了的"和"代码里真的做了的"，是两件事。**

### 下一篇预告

「AI Agent 工程化实战」这个系列写到第 13 篇了，从 LangGraph 的状态循环、MCP 工具解耦、RAG 多租户、SSE 流式、四层降级、测试体系、部署可观测、数据库迁移，一路写到这里。**这条主线基本讲完了。**

如果继续，下一篇想换个视角做一次**复盘**：这 13 篇里哪些设计是"事后觉得对"、哪些是"当时觉得对、现在想改"、以及如果重写一遍会怎么排列优先级。不再是单点技术，而是整个项目的**架构决策清单**。要的话我接着写，还是这个体量。

---

## 参考资料

- **[Ticnix/weather-travel-recommend-system](https://github.com/Ticnix/weather-travel-recommend-system)** —— 项目源码（仍在更新中）
- Anthropic, *Agent Skills* 规范 —— `SKILL.md` frontmatter、`name` / `description` 字段与渐进式披露（progressive disclosure）机制
- 本项目 `backend/app/services/skill_loader.py` —— Skill 扫描、frontmatter 解析与按需加载
- 本项目 `backend/app/services/knowledge_loader.py` —— 段落优先分块器（本文实测对象）
- 本项目 `backend/app/services/rag_service.py` —— pgvector 余弦距离检索（`<=>` 运算符）
- 本项目 `backend/skills/itinerary_planner/SKILL.md` —— "不把模型会听话当作正确性依赖"的纯函数审计设计
- Python 文档, [`str.split`](https://docs.python.org/3/library/stdtypes.html#str.split) —— 段落切分的底层行为
- 本系列第 10 篇《我改了 3 行关键词，测试立刻红了》—— "断言编排，不断言模型输出"的测试原则；本文的 `split_text` 正是一个"没被断言覆盖"的典型
