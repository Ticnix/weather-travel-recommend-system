import os
import sys
from pathlib import Path

BACKEND = Path(r"D:\myproject\weather-travel-recommend-system\backend")
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

from app.services.knowledge_loader import split_text

out = []

# 定位：overlap 只在「累积块被 flush」时写入 current，但下一次循环进入
# if 分支时，current 会被 `current + "\n\n" + para` 覆盖成新内容 ->
# 前面保留的重叠被冲掉了。
# 构造一个能暴露该问题的场景：段落很短，多段共用一个块。

text = "\n\n".join(f"这是第{i}个小段落的内容，用来测试重叠是否保留。" for i in range(1, 21))
out.append(f"输入：20 个小段落，总长 {len(text)}")
parts = split_text(text, 300, 50)
out.append(f"chunk_size=300 overlap=50 -> 块数 {len(parts)}")
for i, p in enumerate(parts):
    out.append(f"  #{i} len={len(p)} :: {p[:45]!r} ... {p[-30:]!r}")

out.append("")
out.append("--- 逐对检查是否重叠（找最长公共片段）---")
def max_overlap(a, b, cap=80):
    best = ""
    for k in range(2, min(cap, len(a)) + 1):
        if a[-k:] in b:
            best = a[-k:]
    return best

for i in range(len(parts) - 1):
    ov = max_overlap(parts[i], parts[i + 1])
    out.append(f"  #{i}->#{i+1}  重叠={len(ov)}字  {ov[:50]!r}")

out.append("")
out.append("--- 结论验证：overlap=0 与 overlap=50 产出的块是否完全相同？---")
p0 = split_text(text, 300, 0)
p50 = split_text(text, 300, 50)
out.append(f"overlap=0  块数={len(p0)} 长度={[len(x) for x in p0]}")
out.append(f"overlap=50 块数={len(p50)} 长度={[len(x) for x in p50]}")
out.append(f"两者内容完全相同？ {p0 == p50}")

Path(r"D:\myproject\weather-travel-recommend-system\.probe_s13e_out.txt").write_text(
    "\n".join(out), encoding="utf-8"
)
