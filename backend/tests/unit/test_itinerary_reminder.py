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

    def test_窗口上限(self):
        assert reminder_tasks.is_due("10:00", _at(9, 25)) is True  # 差 35 分钟，进窗口
        assert reminder_tasks.is_due("10:00", _at(9, 24)) is False  # 差 36 分钟，还早

    def test_太早与已出发都不提醒(self):
        assert reminder_tasks.is_due("10:00", _at(8, 0)) is False
        assert reminder_tasks.is_due("09:00", _at(9, 30)) is False
        assert reminder_tasks.is_due("10:00", _at(10, 0)) is False  # 正好到点
        assert reminder_tasks.is_due("10:00", _at(10, 5)) is False  # 已经出发

    def test_缺少时间或格式不对不提醒(self):
        assert reminder_tasks.is_due(None, _at(9, 30)) is False
        assert reminder_tasks.is_due("上午十点", _at(9, 30)) is False

    def test_窗口比调度间隔宽(self):
        # 窗口 35 分钟 > beat 间隔 10 分钟：一次扫描延迟或 worker 忙都不会漏掉，
        # 重复由发送记录拦住（见 TestReminderDedupe）。
        # 旧实现窗口掐在 25~35 分钟，与 beat 间隔严丝合缝——beat 一抖就永远漏。
        hits = [reminder_tasks.is_due("10:00", _at(9, m)) for m in range(0, 60, 10)]
        assert sum(hits) >= 3


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


class TestReminderDedupe:
    """「只提醒一次」原来靠窗口宽度与调度间隔对齐，现在靠发送记录判重。"""

    async def test_同一行程不会提醒两次(self, db):
        user = await _user(db, "dedupe_user")
        await _itinerary(db, user.id)  # 10:00 出发

        await reminder_tasks.send_due_reminders(db, now=_at(9, 30))
        first = (await db.execute(select(NotificationLog))).scalars().all()
        assert first

        # 10 分钟后再扫：仍在窗口内（还差 20 分钟），但不该再发一次
        stat = await reminder_tasks.send_due_reminders(db, now=_at(9, 40))
        second = (await db.execute(select(NotificationLog))).scalars().all()

        assert len(second) == len(first)
        assert stat["sent"] == 0
        assert stat["skipped"] == 0

    async def test_错过前几次扫描仍能补提醒(self, db):
        # 9:20 还太早，9:40 才扫到（模拟 beat 延迟 / worker 忙 / 服务重启）。
        # 旧窗口是 9:25~9:35，这一条会永远收不到提醒，且没有任何痕迹。
        user = await _user(db, "late_user")
        await _itinerary(db, user.id)

        await reminder_tasks.send_due_reminders(db, now=_at(9, 20))
        assert (await db.execute(select(NotificationLog))).scalars().all() == []

        stat = await reminder_tasks.send_due_reminders(db, now=_at(9, 40))

        assert stat["checked"] == 1
        assert (await db.execute(select(NotificationLog))).scalars().all()

    async def test_发送失败的下一次扫描会重试(self, db):
        user = await _user(db, "retry_user")
        await _itinerary(db, user.id)
        title, body = reminder_tasks.build_reminder(
            Itinerary(user_id=user.id, title="白云山爬山", date="2026-09-16", start_time="10:00")
        )
        db.add(
            NotificationLog(
                user_id=user.id,
                channel="web_push",
                category="itinerary",
                title=title,
                body=body,
                status="failed",
                error="推送服务器连不上",
                created_at=_at(9, 30),
            )
        )
        await db.commit()

        await reminder_tasks.send_due_reminders(db, now=_at(9, 35))

        logs = (await db.execute(select(NotificationLog))).scalars().all()
        # 失败那条不算"已提醒"，所以这次又写入了新的发送记录（两条通道各一条）
        assert len(logs) > 1
        assert any(log.status == "skipped" for log in logs)

    async def test_被偏好拦下后不再重复记录(self, db):
        user = await _user(db, "pref_user")
        await _itinerary(db, user.id)
        pref = await notification_service.get_prefs(db, user.id)
        pref.itinerary_enabled = False
        await db.commit()

        await reminder_tasks.send_due_reminders(db, now=_at(9, 30))
        first = (await db.execute(select(NotificationLog))).scalars().all()
        assert first

        await reminder_tasks.send_due_reminders(db, now=_at(9, 40))
        second = (await db.execute(select(NotificationLog))).scalars().all()

        # skipped 也算"处理过了"：否则关掉开关的用户每 10 分钟被记一条
        assert len(second) == len(first)
