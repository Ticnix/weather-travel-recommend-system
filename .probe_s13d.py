import os
import sys
from pathlib import Path

BACKEND = Path(r"D:\myproject\weather-travel-recommend-system\backend")
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.services.knowledge_loader import split_text

out = []

# 实验：overlap 到底有没有生效？
text = "段落甲" + "甲" * 150 + "\n\n" + "段落乙" + "乙" * 150 + "\n\n" + "段落丙" + "丙" * 150
parts = split_text(text, 300, 50)
out.append(f"输入长度={len(text)}  chunk_size=300 overlap=50")
out.append(f"产出块数={len(parts)}")
for i, p in enumerate(parts):
    out.append(f"  #{i} len={len(p)}  head={p[:20]!r}  tail={p[-20:]!r}")

out.append("")
out.append("--- 检查相邻块是否真的重叠（统计交集字符）---")
for i in range(len(parts) - 1):
    a, b = parts[i], parts[i + 1]
    tail = a[-50:]
    inter = 0
    for k in range(50, 0, -1):
        if tail[-k:] in b[: k + 20]:
            inter = k
            break
    out.append(f"  #{i}->#{i+1} 期望重叠50, 实测尾部出现在下一块开头长度={inter}")

out.append("")
out.append("--- 单段落超长时的滑窗（无 \\n\\n）---")
onetext = "字" * 800
p2 = split_text(onetext, 300, 50)
out.append(f"产出块数={len(p2)} 各块长度={[len(x) for x in p2]}")
out.append("（注：内容全同，无法从文本判断重叠，仅看块数）")

out.append("")
out.append("--- 真实文档 overlap 检查：knowledge_base/guangzhou_transport.md ---")
doc = Path("knowledge_base/guangzhou_transport.md").read_text(encoding="utf-8")
p3 = split_text(doc, 300, 50)
for i in range(len(p3) - 1):
    a, b = p3[i], p3[i + 1]
    found = ""
    for k in range(min(50, len(a)), 1, -1):
        if a[-k:] and a[-k:] in b:
            found = a[-k:]
            break
    out.append(f"  #{i} len={len(a)} | #{i+1} len={len(b)} | 共用片段长度={len(found)} {found[:40]!r}")

Path(r"D:\myproject\weather-travel-recommend-system\.probe_s13d_out.txt").write_text(
    "\n".join(out), encoding="utf-8"
)
