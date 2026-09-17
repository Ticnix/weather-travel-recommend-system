"""天气预警识别与推送测试（Day 36）。

重点覆盖三件事：
- 去重键：什么算「同一条预警」
- 新增识别：重复轮询不能重复推（这是本日最核心的约束）
- 用户匹配：广州面向全体订阅者，异地只推给行程涉及该城市的人
"""

from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.models.itinerary import Itinerary
from app.models.notification import PushSubscription
from app.models.user import User
from app.models.weather_alert import WeatherAlert
from app.services import alert_service


class FakeAlert:
    """模拟上游返回的预警对象（weather_client.WeatherAlert 的最小结构）。"""

    def __init__(
        self,
        level: str = "warn",
        type: str = "rain",
        title: str = "暴雨黄色预警",
        detail: str = "未来 6 小时降水增强",
    ) -> None:
        self.level = level
        self.type = type
        self.title = title
        self.detail = detail


async def _make_subscriber(db, name: str, endpoint: str) -> User:
    """造一个「有推送订阅」的用户（只有这类用户会被预警触达）。"""
    user = User(username=name, password_hash="x", is_active=True)
    db.add(user)
    await db.flush()
    db.add(
        PushSubscription(
            user_id=user.id, endpoint=endpoint, p256dh="key", auth="auth", is_active=True
        )
    )
    await db.commit()
    return user


class TestFingerprint:
    def test_同城同级同标题视为同一条(self):
        assert alert_service.fingerprint("广州", "warn", "暴雨预警") == (
            alert_service.fingerprint("广州", "warn", "暴雨预警")
        )

    def test_城市不同即不是同一条(self):
        assert alert_service.fingerprint("广州", "warn", "暴雨预警") != (
            alert_service.fingerprint("上海", "warn", "暴雨预警")
        )

    def test_级别不同即不是同一条(self):
        assert alert_service.fingerprint("广州", "warn", "暴雨预警") != (
            alert_service.fingerprint("广州", "danger", "暴雨预警")
        )


class TestAlertMessage:
    def test_危险级别用醒目图标(self):
        alert = WeatherAlert(
            fingerprint="f",
            city="广州",
            level="danger",
            type="rain",
            title="暴雨红色预警",
            first_seen_at=datetime.now(),
            last_seen_at=datetime.now(),
        )
        title, _ = alert_service.alert_message(alert)
        assert title.startswith("🚨")
        assert "广州" in title and "暴雨红色预警" in title

    def test_警告级别图标不同(self):
        alert = WeatherAlert(
            fingerprint="f",
            city="广州",
            level="warn",
            type="rain",
            title="大风蓝色预警",
            first_seen_at=datetime.now(),
            last_seen_at=datetime.now(),
        )
        title, _ = alert_service.alert_message(alert)
        assert title.startswith("⚠️")

    def test_超长正文被截断到适合手机展示(self):
        alert = WeatherAlert(
            fingerprint="f",
            city="广州",
            level="warn",
            type="rain",
            title="预警",
            detail="很长" * 200,
            first_seen_at=datetime.now(),
            last_seen_at=datetime.now(),
        )
        _, body = alert_service.alert_message(alert)
        assert len(body) <= 200

    def test_无详情时给兜底文案(self):
        alert = WeatherAlert(
            fingerprint="f",
            city="广州",
            level="warn",
            type="rain",
            title="预警",
            detail=None,
            first_seen_at=datetime.now(),
            last_seen_at=datetime.now(),
        )
        _, body = alert_service.alert_message(alert)
        assert body


class TestSyncCityAlerts:
    async def test_首次同步全部识别为新增(self, db):
        new_alerts = await alert_service.sync_city_alerts(db, "广州", [FakeAlert()])
        await db.commit()
        assert len(new_alerts) == 1
        assert new_alerts[0].city == "广州"

    async def test_重复轮询不产生重复记录(self, db):
        """核心约束：上游每次返回全量预警，第二次轮询不能再算「新增」。"""
        await alert_service.sync_city_alerts(db, "广州", [FakeAlert()])
        await db.commit()

        again = await alert_service.sync_city_alerts(db, "广州", [FakeAlert()])
        await db.commit()
        assert again == []  # 没有新增

        rows = (await db.execute(select(WeatherAlert))).scalars().all()
        assert len(rows) == 1

    async def test_重复轮询会刷新最后出现时间(self, db):
        first = await alert_service.sync_city_alerts(db, "广州", [FakeAlert()])
        await db.commit()
        row = first[0]
        row.last_seen_at = datetime(2020, 1, 1)
        await db.commit()

        await alert_service.sync_city_alerts(db, "广州", [FakeAlert()])
        await db.commit()

        refreshed = (await db.execute(select(WeatherAlert))).scalar_one()
        assert refreshed.last_seen_at.year > 2020

    async def test_新增与已有混合时只返回新增(self, db):
        await alert_service.sync_city_alerts(db, "广州", [FakeAlert(title="暴雨黄色预警")])
        await db.commit()

        new_alerts = await alert_service.sync_city_alerts(
            db,
            "广州",
            [FakeAlert(title="暴雨黄色预警"), FakeAlert(title="台风蓝色预警")],
        )
        await db.commit()
        assert [a.title for a in new_alerts] == ["台风蓝色预警"]


class TestMatchUsers:
    async def test_广州预警面向所有订阅用户(self, db):
        a = await _make_subscriber(db, "alert_gz_a", "https://push/a")
        b = await _make_subscriber(db, "alert_gz_b", "https://push/b")

        matched = await alert_service.match_users(db, "广州")
        assert set(matched) == {a.id, b.id}

    async def test_异地预警只推给行程涉及该城市的用户(self, db):
        travel = await _make_subscriber(db, "alert_sh_travel", "https://push/t")
        stay = await _make_subscriber(db, "alert_sh_stay", "https://push/s")

        soon = (date.today() + timedelta(days=2)).isoformat()
        db.add(
            Itinerary(user_id=travel.id, title="上海迪士尼一日游", date=soon, location="上海迪士尼")
        )
        await db.commit()

        matched = await alert_service.match_users(db, "上海")
        assert matched == [travel.id]  # 只推给出行的用户，不打扰其他人
        assert stay.id not in matched

    async def test_过期行程不参与匹配(self, db):
        user = await _make_subscriber(db, "alert_past", "https://push/p")
        past = (date.today() - timedelta(days=5)).isoformat()
        db.add(Itinerary(user_id=user.id, title="旧行程", date=past, location="上海外滩"))
        await db.commit()

        assert await alert_service.match_users(db, "上海") == []

    async def test_已退订的用户不再匹配(self, db):
        user = await _make_subscriber(db, "alert_unsub", "https://push/u")
        sub = (
            await db.execute(select(PushSubscription).where(PushSubscription.user_id == user.id))
        ).scalar_one()
        sub.is_active = False
        await db.commit()

        assert await alert_service.match_users(db, "广州") == []


class TestPollAndDispatch:
    async def test_新增预警触发推送且重复轮询不再推(self, db, monkeypatch):
        user = await _make_subscriber(db, "alert_push", "https://push/1")

        async def fake_fetch_alerts(city=None):
            return [FakeAlert(level="danger", title="暴雨红色预警")]

        pushed: list[tuple[int, str]] = []
        published: list[dict] = []

        # **_kwargs：notify_user 有 category 等参数，兜住避免签名一变就改测试
        async def fake_notify(session, user_id, title, body, url, **_kwargs):
            pushed.append((user_id, title))
            return {"web_push": {"status": "sent"}, "email": {"status": "skipped"}}

        async def fake_publish(channel, payload):
            published.append(payload)
            return True

        monkeypatch.setattr(alert_service, "fetch_alerts_with_fallback", fake_fetch_alerts)
        monkeypatch.setattr("app.services.notification_service.notify_user", fake_notify)
        monkeypatch.setattr("app.core.event_bus.publish", fake_publish)

        first = await alert_service.poll_and_dispatch(db, cities=["广州"])
        assert first["new_alerts"] == 1
        assert first["pushed_alerts"] == 1
        assert first["notified_users"] == 1
        assert pushed and pushed[0][0] == user.id
        assert published and published[0]["event"] == "weather_alert"
        assert published[0]["level"] == "danger"

        # 第二次轮询：上游仍返回同一条预警，但不该再推
        second = await alert_service.poll_and_dispatch(db, cities=["广州"])
        assert second["new_alerts"] == 0
        assert second["pushed_alerts"] == 0
        assert len(pushed) == 1
        assert len(published) == 1

    async def test_info级别只入库不打扰用户(self, db, monkeypatch):
        await _make_subscriber(db, "alert_info", "https://push/i")

        async def fake_fetch_alerts(city=None):
            return [FakeAlert(level="info", title="能见度较低")]

        pushed: list[int] = []

        async def fake_notify(session, user_id, title, body, url, **_kwargs):
            pushed.append(user_id)
            return {"web_push": {"status": "sent"}}

        monkeypatch.setattr(alert_service, "fetch_alerts_with_fallback", fake_fetch_alerts)
        monkeypatch.setattr("app.services.notification_service.notify_user", fake_notify)

        stat = await alert_service.poll_and_dispatch(db, cities=["广州"])
        assert stat["new_alerts"] == 1  # 入库留痕
        assert stat["pushed_alerts"] == 0  # 但不推送
        assert pushed == []

        rows = (await db.execute(select(WeatherAlert))).scalars().all()
        assert len(rows) == 1

    async def test_上游拉取失败不影响其他城市(self, db, monkeypatch):
        async def flaky_fetch_alerts(city=None):
            if city == "广州":
                raise RuntimeError("上游超时")
            return [FakeAlert(title="上海大风预警")]

        monkeypatch.setattr(alert_service, "fetch_alerts_with_fallback", flaky_fetch_alerts)
        stat = await alert_service.poll_and_dispatch(db, cities=["广州", "上海"])
        assert stat["new_alerts"] == 1  # 广州失败，上海正常入库


class TestAlertFallback:
    """预警兜底：和风的预警接口属付费能力（免费 Key 实测 403），必须有兜底，
    否则「配置为 qweather」时预警推送功能等于从未启用。"""

    async def test_主源有预警时不再调用兜底源(self, monkeypatch):
        from types import SimpleNamespace

        from app.services import weather_service

        async def fake_fetch_weather(city=None):
            return SimpleNamespace(alerts=[FakeAlert(title="官方预警")])

        called: list[str] = []

        async def fake_open_meteo(city):
            called.append(city)
            return SimpleNamespace(alerts=[FakeAlert(title="兜底预警")])

        monkeypatch.setattr(weather_service, "fetch_weather", fake_fetch_weather)
        monkeypatch.setattr(weather_service, "_open_meteo_fetch", fake_open_meteo)
        monkeypatch.setattr(weather_service.settings, "WEATHER_PROVIDER", "qweather")

        alerts = await weather_service.fetch_alerts_with_fallback("广州")
        assert [a.title for a in alerts] == ["官方预警"]
        assert called == []  # 主源有结果就不该多打一次兜底源

    async def test_主源无预警时用兜底源补一次(self, monkeypatch):
        from types import SimpleNamespace

        from app.services import weather_service

        async def fake_fetch_weather(city=None):
            return SimpleNamespace(alerts=[])

        async def fake_open_meteo(city):
            return SimpleNamespace(alerts=[FakeAlert(title="阈值预警")])

        monkeypatch.setattr(weather_service, "fetch_weather", fake_fetch_weather)
        monkeypatch.setattr(weather_service, "_open_meteo_fetch", fake_open_meteo)
        monkeypatch.setattr(weather_service.settings, "WEATHER_PROVIDER", "qweather")

        alerts = await weather_service.fetch_alerts_with_fallback("广州")
        assert [a.title for a in alerts] == ["阈值预警"]

    async def test_主源本身就是免费源时不做多余调用(self, monkeypatch):
        from types import SimpleNamespace

        from app.services import weather_service

        async def fake_fetch_weather(city=None):
            return SimpleNamespace(alerts=[])

        called: list[str] = []

        async def fake_open_meteo(city):
            called.append(city)
            return SimpleNamespace(alerts=[FakeAlert(title="阈值预警")])

        monkeypatch.setattr(weather_service, "fetch_weather", fake_fetch_weather)
        monkeypatch.setattr(weather_service, "_open_meteo_fetch", fake_open_meteo)
        monkeypatch.setattr(weather_service.settings, "WEATHER_PROVIDER", "open_meteo")

        alerts = await weather_service.fetch_alerts_with_fallback("广州")
        assert alerts == []
        assert called == []

    async def test_兜底源失败时按无预警处理(self, monkeypatch):
        from types import SimpleNamespace

        from app.services import weather_service

        async def fake_fetch_weather(city=None):
            return SimpleNamespace(alerts=[])

        async def broken_open_meteo(city):
            raise RuntimeError("兜底源也挂了")

        monkeypatch.setattr(weather_service, "fetch_weather", fake_fetch_weather)
        monkeypatch.setattr(weather_service, "_open_meteo_fetch", broken_open_meteo)
        monkeypatch.setattr(weather_service.settings, "WEATHER_PROVIDER", "qweather")

        assert await weather_service.fetch_alerts_with_fallback("广州") == []
