import os
import re
import sys
from pathlib import Path

ROOT = Path(r"D:\myproject\weather-travel-recommend-system")
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

out = []

def line_count(p: Path):
    try:
        return sum(1 for _ in p.open(encoding="utf-8", errors="ignore"))
    except Exception:
        return -1

# 1. 后端 Python 代码规模（排除 venv / htmlcov / __pycache__）
skip = {"venv", ".venv", "__pycache__", "htmlcov", "node_modules", ".git", "alembic"}
total = 0
files = 0
by_dir = {}
for p in BACKEND.rglob("*.py"):
    parts = set(p.parts)
    if parts & skip:
        continue
    n = line_count(p)
    total += n
    files += 1
    rel = p.relative_to(BACKEND)
    key = str(rel.parts[0]) if len(rel.parts) > 1 else "(root)"
    if len(rel.parts) > 2 and rel.parts[0] == "app":
        key = f"app/{rel.parts[1]}"
    d = by_dir.setdefault(key, [0, 0])
    d[0] += 1
    d[1] += n

out.append(f"后端 Python：{files} 个文件 / {total} 行（已排除 venv/htmlcov/pycache）")
out.append("按目录：")
for k in sorted(by_dir, key=lambda x: -by_dir[x][1]):
    out.append(f"  {k:24s} {by_dir[k][0]:3d} 文件  {by_dir[k][1]:6d} 行")

# 2. 迁移文件
mig = sorted((BACKEND / "alembic" / "versions").glob("*.py"))
out.append(f"\n迁移文件：{len(mig)} 个")
for m in mig:
    out.append(f"  {m.name}")

# 3. 测试文件
tests = [p for p in (BACKEND / "tests").rglob("test_*.py")]
out.append(f"\n测试文件：{len(tests)} 个，共 {sum(line_count(p) for p in tests)} 行")

# 4. MCP 工具数 / 本地工具数
srv = (BACKEND / "mcp_server" / "server.py").read_text(encoding="utf-8")
out.append(f"\nMCP 工具（@mcp.tool）：{srv.count('@mcp.tool()')} 个")
lt = (BACKEND / "app" / "services" / "local_tools.py").read_text(encoding="utf-8")
out.append(f"本地工具（@tool）：{lt.count('@tool')} 个")

# 5. 领域数
reg = (BACKEND / "app" / "services" / "agent_registry.py").read_text(encoding="utf-8")
out.append(f"多 Agent 领域（Domain(）：{reg.count('Domain(')} 个")

# 6. Skill 数
skills = [d for d in (BACKEND / "skills").iterdir() if d.is_dir() and (d / "SKILL.md").is_file()]
out.append(f"Skill：{len(skills)} 个")

# 7. 知识库文档
kb = list((BACKEND / "knowledge_base").glob("*.md"))
out.append(f"知识库文档：{len(kb)} 个")

# 8. 路由数
routers = list((BACKEND / "app" / "routers").glob("*.py"))
out.append(f"\n路由文件：{len(routers)} 个")

# 9. Celery 任务
tasks = [p for p in (BACKEND / "app" / "tasks").glob("*.py")] if (BACKEND / "app" / "tasks").is_dir() else []
task_txt = ""
for t in tasks:
    task_txt += t.read_text(encoding="utf-8", errors="ignore")
out.append(f"@shared_task/@app.task 数：{task_txt.count('@shared_task') + task_txt.count('@app.task')}")

Path(ROOT / ".probe_14_out.txt").write_text("\n".join(out), encoding="utf-8")
