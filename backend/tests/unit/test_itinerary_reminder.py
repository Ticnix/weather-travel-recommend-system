"""出发前行程提醒测试（Day 39）。

时间窗口是这段逻辑里唯一容易出错的地方，
所以把窗口判定拆成纯函数单独测（含边界），再测整体流程。
"""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.models.itinerary import Itinerary
from app.models.notification import NotificationLog
from app.models.user import User
from app.services import notification_service
from app.tasks import reminder_tasks

CN = ZoneInfo("Asia/Shanghai")


def _at(hour: int, minute: int, day: int = 16) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=CN)


async def _user(db, name: str = "remind_user") -> User:
    user = User(username=name, password_hash="x")
    db.add(user)
    await db.commit()
    return user


async def _itinerary(db, user_id: int, start_time: str = "10:00", day: str = "2026-09-16"):
    item = Itinerary(
        user_id=user_id,
        title="白云山爬山",
        date=day,
        start_time=start_time,
        location="白云山",
    )
    db.add(item)
    await db.commit()
    return item


class TestParseStartTime:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("09:30", time(9, 30)),
            ("00:00", time(0, 0)),
            ("23:59", time(23, 59)),
            (None, None),
            ("", None),
            ("上午", None),
            ("99:99", None),
        ],
    )
    def test_解析时间格式(self, value, expected):
        assert reminder_tasks.parse_start_time(value) == expected


class TestIsDue:
    def test_距出发三十分钟时提醒(self):
        assert reminder_tasks.is_due("10:00", _at(9, 30)) is True

    def test_窗口边界(self):
        assert reminder_tasks.is_due("10:00", _at(9, 35)) is True  # 差 25 分钟，进窗口
        assert reminder_tasks.is_due("10:00", _at(9, 25)) is False  # 差 35 分钟，右开
        assert reminder_tasks.is_due("10:00", _at(9, 24)) is False  # 差 36 分钟，还早

    def test_太早与已出发都不提醒(self):
        assert reminder_tasks.is_due("10:00", _at(8, 0)) is False
        assert reminder_tasks.is_due("09:00", _at(9, 30)) is False

    def test_缺少时间或格式不对不提醒(self):
        assert reminder_tasks.is_due(None, _at(9, 30)) is False
        assert reminder_tasks.is_due("上午十点", _at(9, 30)) is False

    def test_每条行程只会命中一个窗口(self):
        # beat 每 10 分钟触发一次，窗口宽度也是 10 分钟 →
        # 一条行程恰好只被提醒一次，因此不需要在库里记「已提醒」
        hits = [reminder_tasks.is_due("10:00", _at(9, m)) for m in range(0, 60, 10)]
        assert sum(hits) == 1


class TestSendDueReminders:
    async def test_到点的行程会走发送流程(self, db):
        user = await _user(db)
        await _itinerary(db, user.id)

        stat = await reminder_tasks.send_due_reminders(db, now=_at(9, 30))

        assert stat["checked"] == 1
        logs = (await db.execute(select(NotificationLog))).scalars().all()
        assert logs
        # 该用户没有订阅也没有邮箱，所以通道 skipped——
        # 但类型必须是 itinerary，用户才知道这条从哪来
        assert all(log.category == "itinerary" for log in logs)
        assert "白云山" in (logs[0].body or "")

    async def test_没到点的行程不动它(self, db):
        user = await _user(db)
        await _itinerary(db, user.id)

        stat = await reminder_tasks.send_due_reminders(db, now=_at(8, 0))

        assert stat["sent"] == 0
        assert (await db.execute(select(NotificationLog))).scalars().all() == []

    async def test_关闭行程提醒后不再打扰(self, db):
        user = await _user(db)
        await _itinerary(db, user.id)
        pref = await notification_service.get_prefs(db, user.id)
        pref.itinerary_enabled = False
        await db.commit()

        await reminder_tasks.send_due_reminders(db, now=_at(9, 30))

        logs = (await db.execute(select(NotificationLog))).scalars().all()
        assert logs
        assert all(log.status == "skipped" for log in logs)
        assert "已关闭" in (logs[0].error or "")

    async def test_其他日期的行程不参与今天(self, db):
        user = await _user(db)
        await _itinerary(db, user.id, day="2026-09-17")

        stat = await reminder_tasks.send_due_reminders(db, now=_at(9, 30))

        assert stat["checked"] == 0

    async def test_没有填写时间的行程被忽略(self, db):
        user = await _user(db)
        db.add(Itinerary(user_id=user.id, title="随便逛逛", date="2026-09-16", start_time=None))
        await db.commit()

        stat = await reminder_tasks.send_due_reminders(db, now=_at(9, 30))

        assert stat["checked"] == 0
