"""Skill 加载器：读取 skills/ 目录下的标准 Skill（Anthropic Agent Skills 规范）。

标准 Skill 结构：
    skills/<skill-name>/
    ├── SKILL.md          # frontmatter(name, description) + 使用说明
    ├── references/       # 参考资料（规则表、指南等 markdown）
    └── scripts/          # 可执行脚本（核心逻辑）

本模块负责：
- 扫描所有 Skill，解析 SKILL.md 的 frontmatter 元信息
- 提供按名称加载 Skill 的能力
- 供 Agent / MCP 工具层发现与使用 Skill
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# skills 目录（backend/skills/）
SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


@dataclass
class SkillMeta:
    """Skill 元信息（来自 SKILL.md 的 frontmatter）。"""

    name: str
    description: str
    path: Path


def _parse_frontmatter(content: str) -> dict[str, str]:
    """解析 SKILL.md 顶部 YAML frontmatter（简化版，支持 name/description）。"""
    meta: dict[str, str] = {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        line = line.strip()
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip().strip("'\"")
    return meta


def list_skills() -> list[SkillMeta]:
    """扫描 skills/ 目录，返回所有 Skill 的元信息。"""
    skills: list[SkillMeta] = []
    if not SKILLS_DIR.is_dir():
        return skills
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        content = skill_md.read_text(encoding="utf-8")
        meta = _parse_frontmatter(content)
        skills.append(
            SkillMeta(
                name=meta.get("name", skill_dir.name),
                description=meta.get("description", ""),
                path=skill_dir,
            )
        )
    return skills


def get_skill(name: str) -> SkillMeta | None:
    """按名称获取 Skill。"""
    for skill in list_skills():
        if skill.name == name or skill.path.name == name:
            return skill
    return None


def load_skill_md(name: str) -> str | None:
    """读取某个 Skill 的 SKILL.md 完整内容。"""
    skill = get_skill(name)
    if not skill:
        return None
    return (skill.path / "SKILL.md").read_text(encoding="utf-8")


def load_reference(name: str, ref_file: str) -> str | None:
    """读取某个 Skill 的 references/ 下的文档。"""
    skill = get_skill(name)
    if not skill:
        return None
    ref_path = skill.path / "references" / ref_file
    if not ref_path.is_file():
        return None
    return ref_path.read_text(encoding="utf-8")
