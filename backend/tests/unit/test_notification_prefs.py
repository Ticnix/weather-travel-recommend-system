"""通知类型偏好测试（Day 39）。

核心约束：**被用户关掉的类型必须拦在发送入口**，并且留下可查的记录——
"为什么没收到"这个问题的答案应该在推送历史里，而不是凭猜。
"""

import pytest
from sqlalchemy import select

from app.models.notification import NotificationLog, NotificationPref
from app.models.user import User
from app.services import notification_service


async def _user(db, name: str = "pref_user") -> User:
    user = User(username=name, password_hash="x")
    db.add(user)
    await db.commit()
    return user


class TestGetPrefs:
    async def test_首次读取按默认值懒初始化(self, db):
        user = await _user(db)
        pref = await notification_service.get_prefs(db, user.id)
        await db.commit()

        # 默认全开——用户没表达过意愿时，默认值应该站在"有用"那一边
        assert pref.morning_enabled is True
        assert pref.alert_enabled is True
        assert pref.itinerary_enabled is True
        assert pref.morning_hour == 7

    async def test_重复读取不会创建多条(self, db):
        user = await _user(db)
        await notification_service.get_prefs(db, user.id)
        await notification_service.get_prefs(db, user.id)
        await db.commit()

        rows = (await db.execute(select(NotificationPref))).scalars().all()
        assert len(rows) == 1


class TestCategoryAllowed:
    @pytest.mark.parametrize(
        ("category", "field"),
        [
            ("morning", "morning_enabled"),
            ("alert", "alert_enabled"),
            ("itinerary", "itinerary_enabled"),
        ],
    )
    async def test_关闭某类型后该类型被拦下(self, db, category, field):
        user = await _user(db)
        pref = await notification_service.get_prefs(db, user.id)
        setattr(pref, field, False)
        await db.commit()

        allowed, reason = await notification_service.category_allowed(db, user.id, category)
        assert allowed is False
        assert "已关闭" in reason

    async def test_系统通知不受任何类型开关影响(self, db):
        user = await _user(db)
        pref = await notification_service.get_prefs(db, user.id)
        pref.morning_enabled = False
        pref.alert_enabled = False
        pref.itinerary_enabled = False
        await db.commit()

        # 测试通知这类诊断消息必须能发出去，否则用户没法自检订阅链路
        allowed, _ = await notification_service.category_allowed(db, user.id, "system")
        assert allowed is True


class TestNotifySuppressed:
    async def test_关掉的类型不发送但留痕(self, db):
        user = await _user(db)
        pref = await notification_service.get_prefs(db, user.id)
        pref.alert_enabled = False
        await db.commit()

        result = await notification_service.notify_user(
            db, user.id, title="暴雨红色预警", body="请注意防范", category="alert"
        )

        assert {r["status"] for r in result.values()} == {"skipped"}
        assert "已关闭" in result["web_push"]["error"]

        logs = (await db.execute(select(NotificationLog))).scalars().all()
        assert logs
        assert all(log.status == "skipped" for log in logs)
        assert all(log.category == "alert" for log in logs)

    async def test_开启时进入正常发送流程(self, db):
        user = await _user(db)
        result = await notification_service.notify_user(
            db, user.id, title="暴雨红色预警", body="请注意防范", category="alert"
        )
        # 该用户既没订阅也没邮箱，通道会各自 skipped，
        # 但原因必须与偏好无关——否则就分不清是"被关了"还是"没通道"
        assert "已关闭" not in (result["web_push"]["error"] or "")

    async def test_发送记录带上通知类型(self, db):
        user = await _user(db)
        await notification_service.notify_user(db, user.id, title="早报", category="morning")

        log = (await db.execute(select(NotificationLog))).scalars().first()
        assert log is not None
        assert log.category == "morning"
