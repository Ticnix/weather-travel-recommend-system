import os
import sys
from pathlib import Path

BACKEND = Path(r"D:\myproject\weather-travel-recommend-system\backend")
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.services.knowledge_loader import split_text

out = []

# 决定性实验：每段内容唯一，段落边界处放一个只出现一次的"锚点词"。
# 若 overlap 生效，锚点词所在句应同时出现在相邻两块里。
paras = []
for i in range(1, 13):
    mark = f"锚点{i:02d}号"
    paras.append(f"{mark}：" + f"内容{i:02d}" * 25)
text = "\n\n".join(paras)
out.append(f"总长={len(text)} 段落数={len(paras)}")

for ov in (0, 50):
    parts = split_text(text, 300, ov)
    out.append(f"\n===== overlap={ov} -> 块数={len(parts)} =====")
    for i, p in enumerate(parts):
        marks = [f"锚点{k:02d}号" for k in range(1, 13) if f"锚点{k:02d}号" in p]
        out.append(f"  #{i} len={len(p)} 含锚点={marks}")

out.append("\n===== 关键判定 =====")
p0 = split_text(text, 300, 0)
p50 = split_text(text, 300, 50)
out.append(f"overlap=0 与 overlap=50 输出相同？ {p0 == p50}")
# 看边界：前一块的最后一个锚点，是否也出现在后一块？
def marks_of(p):
    return [k for k in range(1, 13) if f"锚点{k:02d}号" in p]
for i in range(len(p50) - 1):
    a, b = marks_of(p50[i]), marks_of(p50[i + 1])
    out.append(f"  块#{i} 锚点={a}  ->  块#{i+1} 锚点={b}  边界重叠的锚点={sorted(set(a) & set(b))}")

Path(r"D:\myproject\weather-travel-recommend-system\.probe_s13f_out.txt").write_text(
    "\n".join(out), encoding="utf-8"
)
