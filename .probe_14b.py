import subprocess
from pathlib import Path

ROOT = r"D:\myproject\weather-travel-recommend-system"
out = []

def run(args):
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="ignore")
    return (r.stdout or "").strip()

log = run(["git", "log", "--oneline", "--no-merges", "--reverse"])
lines = [l for l in log.splitlines() if l.strip()]
out.append(f"总提交数（非 merge）：{len(lines)}")
out.append("")
out.append("最早 12 个提交（倒序，最早的在前）：")
for l in lines[:12]:
    out.append("  " + l)
out.append("")
out.append("Day 标记分布（提取每个提交里的 DayN）：")
import re
days = []
for l in lines:
    m = re.search(r"Day\s*(\d+)", l)
    if m:
        days.append(int(m.group(1)))
out.append(f"  含 DayN 的提交数：{len(days)}")
if days:
    out.append(f"  Day 范围：{min(days)} ~ {max(days)}")

out.append("")
out.append("首次提交时间 / 最后提交时间：")
out.append("  first: " + run(["git", "log", "--reverse", "--format=%ai", "--no-merges"]).splitlines()[0])
out.append("  last : " + run(["git", "log", "-1", "--format=%ai", "--no-merges"]))

# 是否所有 submission
Path(Path(ROOT) / ".probe_14b_out.txt").write_text("\n".join(out), encoding="utf-8")
