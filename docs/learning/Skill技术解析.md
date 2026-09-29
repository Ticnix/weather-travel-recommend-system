# Skill 技术解析（新手版）

> 本文档从零讲清楚本项目里的「Skill」是怎么实现的。
> 面向对象：完全不懂 Skill 的小白。看完能回答面试中"Skill 是怎么做的"这类问题。

---

## 一、Skill 到底是什么？

**一句话**：Skill = 把"一项能力"打包成一个文件夹，里面装着「说明 + 资料 + 干活代码」三样东西。

打个比方。餐厅老板想让厨师会做"麻辣香锅"，有两种教法：

- **方式 A（不规范）**：把菜谱念给厨师听，厨师凭记忆做。→ 也就是把规则写死在一个 Python 文件里，改起来乱、AI 难理解。
- **方式 B（Skill）**：给厨师一个文件夹，里面有「菜品说明卡片」(SKILL.md)、「食材做法参考」(references/)、「具体步骤」(scripts/)。改味道只改卡片即可。

**方式 B 就是 Skill**。核心好处：**知识（规则）和逻辑（代码）分离，好维护，且 AI 能理解语义、自动触发。**

---

## 二、标准 Skill 文件夹结构（Anthropic Agent Skills 规范）

本项目严格遵循 Anthropic 提出的 Agent Skills 规范。一个 Skill = 一个文件夹：

```
backend/skills/
├── travel_planning/            # 出行规划 Skill
│   ├── SKILL.md                # ①说明书：何时用 + 怎么用
│   ├── references/             # ②参考资料（规则表 markdown）
│   │   └── scoring-rules.md    #    三维评分规则
│   └── scripts/                # ③干活代码（纯逻辑）
│       └── route_planner.py
├── outfit_recommend/           # 穿搭推荐 Skill
│   ├── SKILL.md
│   ├── references/             # temp/weather/scene/preference 4 个规则文档
│   └── scripts/outfit_engine.py
└── itinerary_reminder/         # 行程天气提醒 Skill
    ├── SKILL.md
    ├── references/reminder-guide.md
    └── scripts/reminder.py
```

### 三样东西各有什么用

| 部分 | 作用 | 类比 |
|------|------|------|
| `SKILL.md` | 告诉 AI "这个能力是干嘛的、何时触发" | 岗位职责说明书 |
| `references/` | 存放规则/知识（markdown 文档） | 参考资料库 |
| `scripts/` | 真正干活的代码（纯逻辑，可独立测试） | 具体执行的人 |

---

## 三、逐个拆解三部分

### ① SKILL.md —— 说明书（最关键）

最顶部那段 `---` 包起来的内容叫 **frontmatter（元信息）**，是 AI 理解 Skill 的入口：

```markdown
---
name: outfit-recommend          # 给 Skill 起名字
description: 穿搭推荐技能。当用户询问"穿什么衣服/怎么穿/穿搭建议"时使用。结合天气、活动场景与用户偏好生成建议。
---

# 穿搭推荐 Skill

## 何时使用
- 用户问"明天穿什么""爬山穿什么""我怕冷穿什么"等

## 工作流程
1. 获取气象参数（温度、天气现象、降水、风力）
2. 按「温度档位 + 天气类型 + 活动场景」匹配规则
3. 应用用户偏好调整
4. RAG 检索穿搭知识库增强
5. 生成自然语言建议
```

**AI 靠 `description` 决定"什么时候调这个能力"**。用户问"明天爬山穿什么"，AI 读到这个描述就明白"这是穿搭问题，用 outfit-recommend"。

### ② references/ —— 参考资料（规则文档）

用 markdown 存规则，方便改、还能被 RAG 检索。以 `temp-rules.md` 为例：

```markdown
# 温度档位穿搭规则
| 档位 | 温度区间 | 基础建议 |
|------|---------|---------|
| 炎热 | ≥30°C | 轻薄透气的棉麻/速干面料，短袖短裤，注意防晒 |
| 温暖 | 22~30°C | 薄长袖/T恤 + 轻薄外套或开衫 |
| 凉爽 | 15~22°C | 卫衣/针织衫 + 夹克或风衣 |
| 寒冷 | <15°C | 厚外套/羽绒服 + 毛衣内搭 |
```

**为什么单独放文档而不是写代码里？** 规则经常要改（如"30 度才算炎热"改成"28 度"），改 markdown 比改代码方便；且文档能被 AI 检索（RAG），实现"知识复用"。

### ③ scripts/ —— 干活代码（纯逻辑）

真正执行的 Python 逻辑，只负责"算出规则和气象参数"，**最终人话回答由大模型（LLM）生成**。以穿搭脚本为例：

```python
# skills/outfit_recommend/scripts/outfit_engine.py

TEMP_RULES = [
    ((30.0, 99.0), "炎热：轻薄透气..."),
    ((22.0, 30.0), "温暖：薄长袖..."),
    ((15.0, 22.0), "凉爽：卫衣..."),
    ((-99.0, 15.0), "寒冷：羽绒服..."),
]

WEATHER_RULES = {"雨": "防滑防水鞋...", "雪": "保暖防滑靴...", ...}
SCENE_RULES   = {"爬山": "防滑登山鞋+速干...", "商务": "正式衬衫...", ...}
PREFERENCE_RULES = {"怕冷": "加一件保暖层", "正式": "商务正装", ...}

async def run(city, scene, preference):
    # 1. 查天气 → 明天 30.5°C 雷阵雨
    weather = await fetch_weather(city)
    # 2. 匹配温度规则
    for (lo, hi), rule in TEMP_RULES:
        if lo <= temp < hi:
            rules.append(rule)        # 命中"炎热"
    # 3. 匹配天气/场景/偏好规则
    ...
    # 4. 拼成"给 AI 看的材料"
    return "今天30度雷阵雨，建议穿轻薄透气+防水+防滑登山鞋..."
    # ↑ 这段材料交给 LLM，由 LLM 组织成最终自然回答
```

**职责边界**：Skill 负责"给 AI 提供材料"，LLM 负责"组织语言生成回答"。这是 Agent 项目里很关键的分工。

---

## 四、怎么让 AI "发现"这些 Skill？—— skill_loader

光有文件夹不够，AI 得能"发现"它们。于是写了 `app/services/skill_loader.py`，像个"技能管理员"：

```python
import re
from pathlib import Path
from dataclasses import dataclass

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"

@dataclass
class SkillMeta:
    name: str
    description: str
    path: Path

def _parse_frontmatter(content: str) -> dict[str, str]:
    """解析 SKILL.md 顶部 --- 之间的 name/description"""
    meta = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip("'\"")
    return meta

def list_skills() -> list[SkillMeta]:
    """扫描 skills/ 下所有 Skill，返回元信息列表"""
    skills = []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        content = skill_md.read_text(encoding="utf-8")
        meta = _parse_frontmatter(content)
        skills.append(SkillMeta(
            name=meta.get("name", skill_dir.name),
            description=meta.get("description", ""),
            path=skill_dir,
        ))
    return skills
```

> 原理：遍历 `skills/` 目录 → 读每个 `SKILL.md` → 用正则提取 frontmatter → 返回 Skill 列表。
> 这样只要新建一个 Skill 文件夹，它就会被自动"登记"，无需手动注册。

---

## 五、怎么让 AI 真正"调用" Skill？—— MCP 工具作为入口

Skill 是"能力打包"，MCP 是"对外调用入口"。两者关系：

- **Skill** = 能力的"知识和逻辑"（文件夹形式，可维护）
- **MCP** = 能力的"调用出口"（让 Agent 通过协议自动触发）
- 配合方式：Skill 定义"做什么、怎么做"，MCP 定义"如何被 AI 发现和调用"

### 第 1 步：注册成 MCP 工具

在 `mcp_server/server.py` 里，把 Skill 脚本包装成 MCP 工具：

```python
@mcp.tool()
async def recommend_outfit(city: str = "广州", scene: str = "", preference: str = "") -> str:
    """穿搭推荐：结合天气+场景+偏好，生成贴合场景的穿搭建议。
    Args:
        city: 城市，默认"广州"。
        scene: 活动场景（爬山/逛街/夜游/商务...），可留空。
        preference: 用户偏好（怕冷/怕热/正式/运动...），可留空。
    """
    return await outfit_engine.run(city, scene or None, preference or None)
```

### 第 2 步：Agent 决策提示词写明"何时用"

在 `app/services/agent.py` 的系统提示词里加规则：

```
7. 若问题涉及穿什么衣服/穿搭建议（如"明天爬山穿什么"），
   则调用 recommend_outfit 穿搭推荐，并把场景和偏好作为参数传入。
```

---

## 六、完整流程串起来（用户问一句，背后发生了什么）

以用户问 "**明天爬山穿什么？**" 为例：

```
① Agent 收到问题
      ↓ 意图识别 → 判断为 "outfit"（穿搭类）
② Agent 回忆提示词规则："穿搭问题 → 调 recommend_outfit"
      ↓
③ 调用 MCP 工具 recommend_outfit("广州", "爬山", "")
      ↓
④ recommend_outfit 内部调 outfit_engine.run()  ← 这就是 Skill 的脚本
      ↓
⑤ 脚本内部：
     → 查天气：明天 30.5°C 雷阵雨
     → 匹配规则：温度"炎热" + 天气"雨天" + 场景"爬山"
     → 得到材料："炎热建议轻薄透气，雨天要防水，爬山要防滑登山鞋"
      ↓
⑥ 规则文本 + 用户问题 一起喂给 LLM
      ↓
⑦ LLM 生成最终人话回答：
   "明天雷阵雨伴冰雹，爬山危险！建议穿速干短袖+防水冲锋衣+防滑登山鞋，
    强烈建议改期；若执意前往务必结伴、避开雷雨时段。"
```

---

## 七、为什么之前"不够规范"，现在改了什么？

### 改造前（不规范）
```python
# app/services/travel_skill.py —— 一个孤零零的 Python 文件
def plan_travel(...):
    ... 评分逻辑写死在代码里 ...
```
问题：
1. 没有 `SKILL.md` → AI 只能靠工具描述理解，不符合规范
2. 规则写死在代码 → 改评分权重得改代码，维护麻烦
3. 不是文件夹 → 不符合业界标准结构，面试说不出手

### 改造后（标准 Skill）
- 每个 Skill 自包含：`SKILL.md` + `references/` + `scripts/`
- 规则拆到 `references/` markdown，改规则不动代码，还能被 RAG 检索
- 用 `skill_loader` 统一发现；用 MCP 工具做调用入口

### 一个技术细节：目录命名
- 目录名用**下划线**（`travel_planning`）：因为 Python `import` 不支持连字符
- `SKILL.md` 内的 `name` 字段用**连字符**（`travel-planning`）：符合 Anthropic 规范（URL 友好）

---

## 八、概念总结图

```
用户问"明天爬山穿什么"
       ↓
Agent（LangGraph 状态机，含意图识别 + 决策规则）
       ↓  决策规则说：这是穿搭问题
       ↓
MCP 工具 recommend_outfit（对外调用入口）
       ↓
Skill 文件夹 outfit_recommend/（能力的完整打包）
  ├── SKILL.md（说明书：何时用）
  ├── references/（规则：温度/天气/场景/偏好）
  └── scripts/（逻辑：查天气 + 匹配规则）
       ↓
结果材料喂给 LLM → 生成最终人话回答
```

---

## 九、面试高频问答

**Q：Skill 和普通函数/工具的区别？**
A：普通函数只有代码；Skill 是"代码 + 说明 + 参考资料"的完整打包，让 AI 能理解语义和触发条件，可维护性、可发现性更强，符合 Anthropic Agent Skills 规范。

**Q：Skill 里逻辑放 scripts、规则放 references，为什么不都写代码里？**
A：规则（温度档位、场景建议）用 markdown 放 references，改规则不用动代码、还能被 RAG 索引；脚本保持纯逻辑，职责清晰、可独立测试。

**Q：Skill 和 MCP 什么关系？**
A：Skill 是能力的"知识和逻辑"载体（文件夹形式）；MCP 是能力的"调用出口"，让 Agent 通过协议自动发现和触发 Skill。两者配合实现能力层与调用层解耦。

**Q：AI 怎么知道什么时候该用哪个 Skill？**
A：靠 `SKILL.md` 的 `description` 字段 + Agent 决策提示词里的规则共同决定。

**Q：新增一个 Skill 要改多少地方？**
A：只需新建一个文件夹（SKILL.md + references + scripts），`skill_loader` 会自动发现；再把它的脚本包成一个 MCP 工具即可，无需改 Agent 核心逻辑。
