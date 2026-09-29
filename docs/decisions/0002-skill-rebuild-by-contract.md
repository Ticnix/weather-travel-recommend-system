# 0002 · skills 目录按"调用方契约"重建

日期：2026-09-24 ｜ 状态：已采纳（原件已从旧镜像找回并替换重建版）

## 背景

`backend/skills/` 整个目录从本地消失且未被 git 跟踪，导致
`local_tools.py` 顶层 import 失败、**后端启动即崩**。
旧镜像层已被回收、git 无历史、备份只有数据库——没有任何现成副本。

## 决策

按**调用方契约**重建：`local_tools.py` 需要 `planner.run(query)` /
`reminder.run(user_id, query)`，`home_service` 需要
`outfit_engine.outfit_structured(city)`——接口以调用方为准，内部实现复用
既有 service（不引新依赖）。

## 后续（同日）

`weather-celery` 容器还在跑 3 天前的旧镜像，`docker cp` 找回了**原件**
（含 SKILL.md/references 与被漏掉的 travel_planning），替换重建版。
重建版验证逻辑（归一化思路）已并入原件文档。

## 教训

1. **未跟踪的目录 = 随时可能消失**：skills 重建后立即进了 git；
2. 丢文件先找**还在跑旧镜像的容器**，那是最完整的快照；
3. `git log --all -- <path>` 要查对路径（当时查了根目录，实际在 backend/ 下）。
