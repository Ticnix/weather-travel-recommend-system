"""生活指数服务测试（Day 37）。

重点：
- 个性化排序是否符合预期（体质偏好 / 行程活动 / 指数自身结论）
- 时序表的 upsert 语义（同日同类不重复、值变化要更新而不是新插一行）
"""

from datetime import date, timedelta

from sqlalchemy import select

from app.models.life_index import LifeIndexRecord
from app.models.user import User
from app.services import index_service


class FakeIndex:
    """模拟和风返回的一条指数。"""

    def __init__(
        self,
        type_code: str = "2",
        name: str = "洗车指数",
        level: str = "4",
        category: str = "不宜",
        text: str = "未来 24 小时内有雨",
        day: str | None = None,
    ) -> None:
        self.date = day or date.today().isoformat()
        self.type_code = type_code
        self.name = name
        self.level = level
        self.category = category
        self.text = text


def _rec(type_code: str, name: str, category: str, text: str = "") -> LifeIndexRecord:
    """造一条未入库的指数记录，用于纯排序测试。"""
    return LifeIndexRecord(
        city="广州",
        date=date.today().isoformat(),
        type_code=type_code,
        name=name,
        level="1",
        category=category,
        text=text,
    )


SAMPLE = [
    _rec("1", "运动指数", "较不宜"),
    _rec("2", "洗车指数", "不宜"),
    # 刻意用「舒适」而非「炎热」：炎热会额外触发防晒/舒适度加权，
    # 那是另一条规则（单独测），混在一起就看不出是哪条规则在起作用
    _rec("3", "穿衣指数", "舒适"),
    _rec("5", "紫外线指数", "中等"),
    _rec("8", "舒适度指数", "不舒适"),
    _rec("9", "感冒指数", "少发"),
    _rec("14", "晾晒指数", "不宜"),
    _rec("16", "防晒指数", "强"),
]


def _codes(ranked: list[dict]) -> list[str]:
    return [item["type_code"] for item in ranked]


class TestRankIndices:
    def test_默认排序把人人都会看的指数排前面(self):
        assert _codes(index_service.rank_indices(SAMPLE))[:2] == ["3", "5"]

    def test_怕冷的人先看到穿衣与感冒(self):
        codes = _codes(index_service.rank_indices(SAMPLE, "cold"))
        assert codes[0] == "3"
        assert "9" in codes[:4]

    def test_怕热的人先看到舒适度(self):
        codes = _codes(index_service.rank_indices(SAMPLE, "heat"))
        assert codes[0] == "8"

    def test_爬山行程把运动指数提前(self):
        base = _codes(index_service.rank_indices(SAMPLE))
        hiking = _codes(index_service.rank_indices(SAMPLE, "normal", ["白云山爬山"]))
        assert hiking.index("1") < base.index("1")

    def test_洗车行程把洗车指数提前(self):
        base = _codes(index_service.rank_indices(SAMPLE))
        wash = _codes(index_service.rank_indices(SAMPLE, "normal", ["周末洗车"]))
        assert wash.index("2") < base.index("2")

    def test_炎热时防晒指数被加权(self):
        cool = [
            _rec("3", "穿衣指数", "舒适"),
            _rec("8", "舒适度指数", "舒适"),
            _rec("9", "感冒指数", "少发"),
            _rec("16", "防晒指数", "弱"),
        ]
        hot = [
            _rec("3", "穿衣指数", "炎热"),
            _rec("8", "舒适度指数", "不舒适"),
            _rec("9", "感冒指数", "少发"),
            _rec("16", "防晒指数", "强"),
        ]
        assert _codes(index_service.rank_indices(hot)).index("16") < _codes(
            index_service.rank_indices(cool)
        ).index("16")

    def test_同权重时排序稳定不受输入顺序影响(self):
        # 稳定排序很重要：同一份数据每次渲染顺序不同会让界面"跳"
        assert _codes(index_service.rank_indices(SAMPLE)) == _codes(
            index_service.rank_indices(list(reversed(SAMPLE)))
        )

    def test_未知偏好按默认处理(self):
        assert _codes(index_service.rank_indices(SAMPLE, "unknown")) == _codes(
            index_service.rank_indices(SAMPLE)
        )

    def test_空列表不报错(self):
        assert index_service.rank_indices([]) == []


class TestSyncIndices:
    async def test_首次同步写入全部指数(self, db):
        changed = await index_service.sync_indices(db, "广州", [FakeIndex("1"), FakeIndex("2")])
        await db.commit()
        assert changed == 2

        rows = (await db.execute(select(LifeIndexRecord))).scalars().all()
        assert len(rows) == 2

    async def test_重复同步不产生重复行(self, db):
        await index_service.sync_indices(db, "广州", [FakeIndex("2")])
        await db.commit()

        changed = await index_service.sync_indices(db, "广州", [FakeIndex("2")])
        await db.commit()

        assert changed == 0  # 值没变就不算变更
        rows = (await db.execute(select(LifeIndexRecord))).scalars().all()
        assert len(rows) == 1

    async def test_指数随天气变化时更新而不是新插一行(self, db):
        await index_service.sync_indices(db, "广州", [FakeIndex("2", category="不宜")])
        await db.commit()

        # 转晴后洗车指数从「不宜」变「适宜」
        changed = await index_service.sync_indices(db, "广州", [FakeIndex("2", category="适宜")])
        await db.commit()

        assert changed == 1
        rows = (await db.execute(select(LifeIndexRecord))).scalars().all()
        assert len(rows) == 1
        assert rows[0].category == "适宜"

    async def test_不同城市的同类指数互不干扰(self, db):
        await index_service.sync_indices(db, "广州", [FakeIndex("5", category="中等")])
        await index_service.sync_indices(db, "上海", [FakeIndex("5", category="很强")])
        await db.commit()

        rows = (await db.execute(select(LifeIndexRecord))).scalars().all()
        assert len(rows) == 2
        assert {r.city: r.category for r in rows} == {"广州": "中等", "上海": "很强"}

    async def test_多天数据按日期分别入库(self, db):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        await index_service.sync_indices(
            db, "广州", [FakeIndex("5", day=yesterday), FakeIndex("5", category="中等")]
        )
        await db.commit()

        rows = (await db.execute(select(LifeIndexRecord))).scalars().all()
        assert len(rows) == 2

    async def test_上游无数据时不做任何写入(self, db):
        assert await index_service.sync_indices(db, "广州", []) == 0


class TestGetSummary:
    async def test_摘要按偏好排序并被截断(self, db):
        user = User(username="idx_cold", password_hash="x", body_preference="cold")
        db.add(user)
        await db.commit()

        await index_service.sync_indices(
            db, "广州", [FakeIndex(code) for code in ("1", "2", "3", "5", "8", "9", "16")]
        )
        await db.commit()

        summary = await index_service.get_summary(db, "广州", user, size=3)
        assert len(summary) == 3
        assert summary[0]["type_code"] == "3"  # 怕冷 → 穿衣指数最前

    async def test_没有数据时返回空列表(self, db, monkeypatch):
        async def no_data(city, type_code="0"):
            return []

        monkeypatch.setattr(index_service._qweather, "fetch_indices", no_data)
        assert await index_service.get_summary(db, "广州", None, 3) == []


class TestGetHistory:
    async def test_历史按日期升序返回(self, db):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        await index_service.sync_indices(
            db,
            "广州",
            [FakeIndex("5", category="中等"), FakeIndex("5", category="很强", day=yesterday)],
        )
        await db.commit()

        history = await index_service.get_history(db, "广州", "5", days=7)
        assert history["name"] == "紫外线指数"
        assert [p["date"] for p in history["points"]] == [yesterday, date.today().isoformat()]
        assert [p["category"] for p in history["points"]] == ["很强", "中等"]

    async def test_超出天数范围的记录不被返回(self, db):
        old = (date.today() - timedelta(days=60)).isoformat()
        await index_service.sync_indices(db, "广州", [FakeIndex("5", day=old)])
        await db.commit()

        history = await index_service.get_history(db, "广州", "5", days=7)
        assert history["points"] == []


class TestTypeCodeConsistency:
    """编码一致性：权重/偏好里引用的编码必须都在 TYPE_NAMES 里有定义。

    防的是一类很隐蔽的 bug：编码写错不会报任何错，只会让排序"莫名奇怪"。
    真实案例——和风文档里 10/11 的顺序与接口实际返回相反，
    按文档把「空调开启」当成 10 去加权，结果把「空气污染扩散」排到了前面，
    界面上看起来只是"顺序有点怪"，不查真实数据根本发现不了。
    """

    def test_基础权重引用的编码都已定义(self):
        assert not (set(index_service.BASE_WEIGHTS) - set(index_service.TYPE_NAMES))

    def test_偏好引用的编码都已定义(self):
        for preference, codes in index_service.PREFERENCE_HINTS.items():
            missing = set(codes) - set(index_service.TYPE_NAMES)
            assert not missing, f"{preference} 引用了未定义的编码：{missing}"

    def test_活动提示引用的编码都已定义(self):
        for _keywords, codes in index_service.ACTIVITY_HINTS:
            assert not (set(codes) - set(index_service.TYPE_NAMES))

    def test_空调指数编码与接口一致(self):
        # 实测：11 才是「空调开启指数」，10 是「空气污染扩散条件指数」
        assert index_service.TYPE_NAMES["11"] == "空调开启指数"
        assert "11" in index_service.PREFERENCE_HINTS["heat"]
