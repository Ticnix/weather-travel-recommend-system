"""每日早报测试：文本组装、分发过滤、免打扰开关。"""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.notification import NotificationPref
from app.models.user import User
from app.services.daily_report import build_report_text, dispatch_to_users


@pytest.fixture
async def report_factory():
    """测试库的 session factory（与 conftest 同库，独立引擎便于 dispose）。"""
    engine = create_async_engine(settings.DB_URL, poolclass=NullPool)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def _dashboard(**overrides):
    """构造一份最小看板数据（字段结构与 home_service.build_dashboard 一致）。"""
    base = {
        "city": "广州",
        "date": "2026-09-15",
        "weather": {
            "city": "广州",
            "desc": "雷阵雨",
            "temperature": 30.5,
            "feels_like": 35.0,
            "humidity": 80,
            "temp_min": 25.0,
            "temp_max": 33.0,
            "precip": 12.0,
        },
        "tips": [
            {"icon": "⚠️", "level": "danger", "title": "暴雨黄色预警", "text": "未来6小时降水增强"},
            {"icon": "🌦️", "level": "info", "title": "降水明显", "text": "出门带伞"},
        ],
        "outfit": {"suggestion": "轻薄透气为主，带件薄外套", "rules": [], "temp_rule": ""},
        "itinerary": {
            "upcoming": [
                {
                    "date": "2026-09-15",
                    "title": "白云山爬山",
                    "location": "白云山",
                    "weather_hint": "雷阵雨，33°C，降水 12mm；建议带雨具或考虑改期",
                }
            ],
            "total": 1,
        },
        "logged_in": True,
    }
    base.update(overrides)
    return base


class TestBuildReportText:
    def test_标题含天气与温度区间(self):
        title, _ = build_report_text(_dashboard())
        assert "雷阵雨" in title
        assert "33~25" in title

    def test_预警提醒优先展示(self):
        _, body = build_report_text(_dashboard())
        lines = body.split("\n")
        assert "暴雨黄色预警" in lines[0]  # danger 级别的提醒排最前

    def test_今日行程带天气冲突提示(self):
        _, body = build_report_text(_dashboard())
        assert "今日行程「白云山爬山」" in body
        assert "建议带雨具或考虑改期" in body  # 降水 >= 10mm 的冲突提示

    def test_无行程时给通用提示而不是空推送(self):
        dash = _dashboard(itinerary={"upcoming": [], "total": 0})
        _, body = build_report_text(dash)
        assert "今天没有安排行程" in body

    def test_穿搭建议在正文中(self):
        _, body = build_report_text(_dashboard())
        assert "轻薄透气" in body

    def test_天气源全挂时仍能组装(降级为纯提醒):
        dash = _dashboard(weather={}, tips=[], outfit=None, itinerary={"upcoming": [], "total": 0})
        title, body = build_report_text(dash)
        assert title  # 至少有标题
        assert body  # 至少有通用提示


class TestDispatch:
    async def test_只分发给到点的用户(self, db, monkeypatch, report_factory):
        """A 设 7 点、B 设 8 点：hour=7 的分发只应包含 A。"""
        user_a = User(username="report_a", password_hash="x", is_active=True)
        user_b = User(username="report_b", password_hash="x", is_active=True)
        db.add_all([user_a, user_b])
        await db.flush()
        db.add_all(
            [
                NotificationPref(user_id=user_a.id, morning_enabled=True, morning_hour=7),
                NotificationPref(user_id=user_b.id, morning_enabled=True, morning_hour=8),
            ]
        )
        await db.commit()

        async def fake_dashboard(uid):
            return _dashboard()

        calls: list[int] = []

        # **_kwargs：notify_user 新增了 category 等参数，
        # 用 **kwargs 兜住，避免签名一变就要跟着改测试
        async def fake_notify(session, uid, title, body, url, **_kwargs):
            calls.append(uid)
            return {"web_push": {"status": "skipped"}, "email": {"status": "skipped"}}

        monkeypatch.setattr("app.services.daily_report.build_dashboard", fake_dashboard)
        monkeypatch.setattr(
            "app.services.daily_report.notification_service.notify_user", fake_notify
        )

        result = await dispatch_to_users(7, report_factory)
        assert result["targets"] == 1
        assert calls == [user_a.id]

    async def test_关闭开关后不再推送(self, db, monkeypatch, report_factory):
        """免打扰开关：morning_enabled=False 的用户即使到点也不推送。"""
        user = User(username="report_off", password_hash="x", is_active=True)
        db.add(user)
        await db.flush()
        db.add(NotificationPref(user_id=user.id, morning_enabled=False, morning_hour=7))
        await db.commit()

        async def fake_dashboard(uid):
            return _dashboard()

        calls: list[int] = []

        # **_kwargs：notify_user 新增了 category 等参数，
        # 用 **kwargs 兜住，避免签名一变就要跟着改测试
        async def fake_notify(session, uid, title, body, url, **_kwargs):
            calls.append(uid)
            return {"web_push": {"status": "skipped"}, "email": {"status": "skipped"}}

        monkeypatch.setattr("app.services.daily_report.build_dashboard", fake_dashboard)
        monkeypatch.setattr(
            "app.services.daily_report.notification_service.notify_user", fake_notify
        )

        result = await dispatch_to_users(7, report_factory)
        assert result["targets"] == 0
        assert calls == []

    async def test_单用户失败不影响其他人(self, db, monkeypatch, report_factory):
        user_a = User(username="report_ok", password_hash="x", is_active=True)
        user_bad = User(username="report_bad", password_hash="x", is_active=True)
        db.add_all([user_a, user_bad])
        await db.flush()
        db.add_all(
            [
                NotificationPref(user_id=user_a.id, morning_enabled=True, morning_hour=7),
                NotificationPref(user_id=user_bad.id, morning_enabled=True, morning_hour=7),
            ]
        )
        await db.commit()

        async def fake_dashboard(uid):
            if uid == user_bad.id:
                raise RuntimeError("该用户的行程查询炸了")
            return _dashboard()

        async def fake_notify(session, uid, title, body, url, **_kwargs):
            return {"web_push": {"status": "sent"}, "email": {"status": "skipped"}}

        monkeypatch.setattr("app.services.daily_report.build_dashboard", fake_dashboard)
        monkeypatch.setattr(
            "app.services.daily_report.notification_service.notify_user", fake_notify
        )

        result = await dispatch_to_users(7, report_factory)
        assert result["targets"] == 2
        assert result["sent"] == 1  # 只有正常的那位送达
        assert result["failed"] == 1
