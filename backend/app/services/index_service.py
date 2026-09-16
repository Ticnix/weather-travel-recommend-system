"""生活指数服务（Day 37）。

和风 /indices/1d 每天返回当日各类指数（穿衣/紫外线/运动/洗车/感冒…），
但接口本身**不保留历史**。本服务做三件事：

1. **同步入库**：把当日指数 upsert 进 life_indices（城市+日期+类型 唯一），
   这样才有了「这几天紫外线在变强」这类历史对比能力
2. **个性化排序**：同一批指数，不同用户关心的顺序不同——怕冷的先看穿衣与感冒，
   有户外行程的先看运动与紫外线。排序依据全部来自真实信号：
   用户体质偏好 + 近 7 天行程活动 + 指数自身的结论
3. **摘要输出**：首页只展示最相关的几个，避免 16 个指数铺满屏幕

**为什么是排序而不是筛选**：指数是官方给的完整信息，用户偶尔也会想看别的。
全给出来、把最相关的排前面，比替用户决定「你看这几个就够了」更合适。
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.itinerary import Itinerary
from app.models.life_index import LifeIndexRecord
from app.services.qweather_client import QWeatherClient

logger = logging.getLogger(__name__)

_qweather = QWeatherClient()

SUMMARY_SIZE = 4  # 首页展示几个（4 个正好一排卡片）
HISTORY_DAYS = 14  # 历史对比默认回看天数
ACTIVITY_LOOKAHEAD_DAYS = 7  # 行程向后看几天

# 和风指数编码 → 中文名（仅作兜底，正常以接口返回的 name 为准）
#
# ⚠️ 这份映射是**按真实响应校正过**的：和风文档里 10/11 的顺序与接口实际返回相反
# （实测 10=空气污染扩散条件、11=空调开启），7 实际叫「过敏指数」而非「花粉过敏指数」。
# 权重计算依赖编码，映射错了会导致"给空调加权、结果把空气污染排到前面"。
TYPE_NAMES: dict[str, str] = {
    "1": "运动指数",
    "2": "洗车指数",
    "3": "穿衣指数",
    "4": "钓鱼指数",
    "5": "紫外线指数",
    "6": "旅游指数",
    "7": "过敏指数",
    "8": "舒适度指数",
    "9": "感冒指数",
    "10": "空气污染扩散条件指数",
    "11": "空调开启指数",
    "12": "太阳镜指数",
    "13": "化妆指数",
    "14": "晾晒指数",
    "15": "交通指数",
    "16": "防晒指数",
}

# 基础权重：穿衣/紫外线/运动是人人都会看的
BASE_WEIGHTS: dict[str, int] = {
    "3": 30,
    "5": 30,
    "1": 25,
    "8": 25,
    "9": 20,
    "16": 15,
    "2": 10,
    "14": 10,
}

# 体质偏好 → 额外加权的指数类型
PREFERENCE_HINTS: dict[str, tuple[str, ...]] = {
    "cold": ("3", "9", "8"),  # 怕冷：穿衣、感冒、舒适度
    "heat": ("8", "16", "11"),  # 怕热：舒适度、防晒、空调开启（11 是与接口一致的编码）
}

# 行程活动关键词 → 该活动更在意的指数类型
ACTIVITY_HINTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("爬山", "徒步", "骑行", "跑步", "运动", "露营", "球"), ("1", "5", "8")),
    (("洗车",), ("2",)),
    (("钓鱼",), ("4",)),
    (("拍照", "摄影", "逛街", "夜游", "赏花"), ("5", "12", "13")),
    (("晾晒", "晒被子", "晒"), ("14",)),
    (("自驾", "开车", "出行", "通勤", "出差"), ("15",)),
)


def to_dict(record: LifeIndexRecord) -> dict[str, Any]:
    """转成接口输出结构。"""
    return {
        "date": record.date,
        "type_code": record.type_code,
        "name": record.name or TYPE_NAMES.get(record.type_code, ""),
        "level": record.level,
        "category": record.category,
        "text": record.text,
    }


def rank_indices(
    records: list[LifeIndexRecord],
    body_preference: str = "normal",
    activities: list[str] | None = None,
) -> list[dict[str, Any]]:
    """按「与这个用户的相关度」排序。

    权重来源（都是真实信号，没有凭空猜测）：
    1. 基础权重——穿衣/紫外线/运动这类人人都会看
    2. 体质偏好——怕冷则穿衣、感冒、舒适度前置
    3. 行程活动——有爬山则运动、紫外线前置；有洗车行程则洗车指数前置
    4. 指数自身的结论——穿衣指数说「炎热」，就把防晒与舒适度提上来
       （复用指数已经算好的结论，不为排序再多打一次天气接口）

    排序是稳定的（同权重按类型编码），便于测试与前端渲染不跳动。
    """
    scores = dict(BASE_WEIGHTS)

    for code in PREFERENCE_HINTS.get(body_preference or "normal", ()):
        scores[code] = scores.get(code, 10) + 25

    for activity in activities or []:
        for keywords, codes in ACTIVITY_HINTS:
            if any(keyword in activity for keyword in keywords):
                for code in codes:
                    scores[code] = scores.get(code, 10) + 20

    by_code = {r.type_code: r for r in records}
    dress = by_code.get("3")
    if dress and "炎热" in (dress.category or ""):
        # 热天里防晒与舒适度才真正影响出行决策
        scores["16"] = scores.get("16", 10) + 15
        scores["8"] = scores.get("8", 10) + 15

    return sorted(
        (to_dict(r) for r in records),
        key=lambda item: (-scores.get(item["type_code"], 0), item["type_code"]),
    )


async def sync_indices(db: AsyncSession, city: str, indices: list[Any] | None = None) -> int:
    """把指数写入时序表（同城市+日期+类型 走更新而非新插），返回变更条数。

    不传 indices 时自行拉取和风接口。
    """
    items = indices if indices is not None else await _qweather.fetch_indices(city)
    if not items:
        return 0

    # 接口可能一次返回多天，按日期分组处理
    by_date: dict[str, list[Any]] = {}
    for item in items:
        by_date.setdefault(item.date or date.today().isoformat(), []).append(item)

    changed = 0
    for day, day_items in by_date.items():
        rows = (
            (
                await db.execute(
                    select(LifeIndexRecord).where(
                        LifeIndexRecord.city == city, LifeIndexRecord.date == day
                    )
                )
            )
            .scalars()
            .all()
        )
        existing = {row.type_code: row for row in rows}

        for item in day_items:
            row = existing.get(item.type_code)
            if row is None:
                db.add(
                    LifeIndexRecord(
                        city=city,
                        date=day,
                        type_code=item.type_code,
                        name=item.name,
                        level=item.level,
                        category=item.category,
                        text=item.text,
                    )
                )
                changed += 1
            elif (row.level, row.category, row.text) != (item.level, item.category, item.text):
                # 同一天内指数可能随天气更新（比如转晴后洗车指数从「不宜」变「适宜」）
                row.name = item.name
                row.level = item.level
                row.category = item.category
                row.text = item.text
                changed += 1

    await db.flush()
    return changed


async def get_indices(
    db: AsyncSession, city: str, *, allow_fetch: bool = True
) -> list[LifeIndexRecord]:
    """取今日指数：优先读库；库里没有今天的就实时拉一次并落库。"""
    today = date.today().isoformat()

    async def _query() -> list[LifeIndexRecord]:
        rows = await db.execute(
            select(LifeIndexRecord).where(
                LifeIndexRecord.city == city, LifeIndexRecord.date == today
            )
        )
        return list(rows.scalars().all())

    rows = await _query()
    if rows or not allow_fetch:
        return rows

    try:
        await sync_indices(db, city)
        await db.commit()
    except Exception as exc:  # noqa: BLE001 指数失败不该拖垮首页
        logger.warning("生活指数拉取失败 %s: %s", city, exc)
        return []
    return await _query()


async def recent_activities(
    db: AsyncSession, user_id: int, days: int = ACTIVITY_LOOKAHEAD_DAYS
) -> list[str]:
    """取用户近期的行程活动关键词——个性化排序的输入之一。"""
    today = date.today().isoformat()
    end = (date.today() + timedelta(days=days)).isoformat()
    rows = await db.execute(
        select(Itinerary.activity, Itinerary.title).where(
            Itinerary.user_id == user_id,
            Itinerary.date >= today,
            Itinerary.date <= end,
        )
    )
    # activity 可能没填，用 title 兜底（「白云山爬山」也能被关键词命中）
    return [value for pair in rows.all() for value in pair if value]


async def get_summary(
    db: AsyncSession, city: str, user: Any = None, size: int = SUMMARY_SIZE
) -> list[dict[str, Any]]:
    """首页用的指数摘要（已按该用户的相关度排序）。"""
    records = await get_indices(db, city)
    if not records:
        return []

    preference = (getattr(user, "body_preference", None) or "normal") if user else "normal"
    activities = await recent_activities(db, user.id) if user is not None else []
    return rank_indices(records, preference, activities)[:size]


async def get_history(
    db: AsyncSession, city: str, type_code: str, days: int = HISTORY_DAYS
) -> dict[str, Any]:
    """某类指数的历史走势（「这几天紫外线在变强吗」这类对比）。"""
    start = (date.today() - timedelta(days=days)).isoformat()
    rows = await db.execute(
        select(LifeIndexRecord)
        .where(
            LifeIndexRecord.city == city,
            LifeIndexRecord.type_code == type_code,
            LifeIndexRecord.date >= start,
        )
        .order_by(LifeIndexRecord.date)
    )
    return {
        "city": city,
        "type_code": type_code,
        "name": TYPE_NAMES.get(type_code, ""),
        "days": days,
        "points": [to_dict(r) for r in rows.scalars().all()],
    }


async def summary_for_home(user_id: int | None, city: str) -> list[dict[str, Any]]:
    """首页 / 早报入口：自己开会话。

    home_service 手上没有 session（沿用项目里「服务按需自建会话」的约定，
    见 itinerary_service），所以这里提供一个自管会话的包装。
    """
    from app.db.session import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id) if user_id is not None else None
        return await get_summary(db, city, user)
