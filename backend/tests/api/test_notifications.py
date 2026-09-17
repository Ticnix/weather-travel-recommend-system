"""通知接口测试：订阅管理、发送记录、测试推送。

不 mock 推送库的用例都依赖一个事实：未订阅 / 未配置 SMTP 时
notification_service 会记 skipped 而不是真的外发——
这本身就是「友好降级」的验证。
"""

from sqlalchemy import select

from app.models.notification import NotificationLog, PushSubscription

FAKE_ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"


class TestVapidKey:
    async def test_未登录不能获取公钥(self, client):
        resp = await client.get("/api/v1/notifications/vapid-key")
        assert resp.status_code == 401

    async def test_返回公钥(self, client, auth_headers):
        resp = await client.get("/api/v1/notifications/vapid-key", headers=auth_headers)
        assert resp.status_code == 200
        assert len(resp.json()["data"]["publicKey"]) > 40  # P-256 公钥的 base64url


class TestSubscription:
    async def test_保存订阅(self, client, auth_headers, db):
        resp = await client.post(
            "/api/v1/notifications/subscriptions",
            headers=auth_headers,
            json={
                "endpoint": FAKE_ENDPOINT,
                "keys": {"p256dh": "p256dh-key", "auth": "auth-key"},
                "user_agent": "pytest",
            },
        )
        assert resp.status_code == 200
        sub = (
            await db.execute(
                select(PushSubscription).where(PushSubscription.endpoint == FAKE_ENDPOINT)
            )
        ).scalar_one()
        assert sub.p256dh == "p256dh-key"

    async def test_重复订阅幂等不产生重复记录(self, client, auth_headers, db):
        payload = {
            "endpoint": FAKE_ENDPOINT,
            "keys": {"p256dh": "new-key", "auth": "new-auth"},
        }
        for _ in range(2):
            await client.post(
                "/api/v1/notifications/subscriptions", headers=auth_headers, json=payload
            )
        subs = (
            (
                await db.execute(
                    select(PushSubscription).where(PushSubscription.endpoint == FAKE_ENDPOINT)
                )
            )
            .scalars()
            .all()
        )
        assert len(subs) == 1  # upsert：以 endpoint 为唯一键刷新
        assert subs[0].p256dh == "new-key"

    async def test_参数缺失被拒(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/notifications/subscriptions",
            headers=auth_headers,
            json={"endpoint": FAKE_ENDPOINT},  # 缺 keys
        )
        assert resp.status_code == 422

    async def test_退订自己的订阅(self, client, auth_headers, db):
        await client.post(
            "/api/v1/notifications/subscriptions",
            headers=auth_headers,
            json={"endpoint": FAKE_ENDPOINT, "keys": {"p256dh": "k", "auth": "a"}},
        )
        resp = await client.post(
            "/api/v1/notifications/subscriptions/unsubscribe",
            headers=auth_headers,
            json={"endpoint": FAKE_ENDPOINT},
        )
        assert resp.status_code == 200
        sub = (
            await db.execute(
                select(PushSubscription).where(PushSubscription.endpoint == FAKE_ENDPOINT)
            )
        ).scalar_one_or_none()
        assert sub is None


class TestSendAndLogs:
    async def test_测试推送走通且记录可查(self, client, auth_headers, db):
        """未订阅/未配 SMTP 时应为 skipped（友好降级），且发送记录落库。"""
        resp = await client.post("/api/v1/notifications/test", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["web_push"]["status"] == "skipped"  # 没有订阅
        assert data["email"]["status"] == "skipped"  # SMTP 未配置

        # 发送记录可查询（Day 34 检查清单）
        logs = await client.get("/api/v1/notifications/logs", headers=auth_headers)
        items = logs.json()["data"]["items"]
        assert len(items) == 2  # 两个通道各一条
        assert {it["channel"] for it in items} == {"web_push", "email"}

        # 数据库层面也应有记录
        count = len((await db.execute(select(NotificationLog))).scalars().all())
        assert count == 2


class TestMorningReportPrefs:
    """每日早报偏好（Day 35）：开关 + 推送小时。"""

    async def test_未设置时返回默认值(self, client, auth_headers):
        resp = await client.get("/api/v1/notifications/morning-report", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data == {"enabled": True, "hour": 7}

    async def test_设置后可查回(self, client, auth_headers):
        resp = await client.put(
            "/api/v1/notifications/morning-report",
            headers=auth_headers,
            json={"enabled": False, "hour": 8},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == {"enabled": False, "hour": 8}

        resp = await client.get("/api/v1/notifications/morning-report", headers=auth_headers)
        assert resp.json()["data"] == {"enabled": False, "hour": 8}

    async def test_推送小时超出范围被拒(self, client, auth_headers):
        resp = await client.put(
            "/api/v1/notifications/morning-report",
            headers=auth_headers,
            json={"enabled": True, "hour": 3},  # 只允许 5~22 点
        )
        assert resp.status_code == 422

    async def test_未登录不能读写偏好(self, client):
        assert (await client.get("/api/v1/notifications/morning-report")).status_code == 401
        assert (
            await client.put(
                "/api/v1/notifications/morning-report", json={"enabled": True, "hour": 7}
            )
        ).status_code == 401


class TestAlertStream:
    """预警实时通道（SSE over fetch）。"""

    async def test_未登录不能建立实时通道(self, client):
        resp = await client.get("/api/v1/notifications/stream")
        assert resp.status_code == 401

    async def test_通道按SSE格式下发预警事件(self, client, auth_headers, monkeypatch):
        async def fake_subscribe(channel):
            yield {
                "event": "weather_alert",
                "id": 7,
                "city": "广州",
                "level": "danger",
                "alert_type": "rain",
                "title": "暴雨红色预警",
                "detail": "3 小时内降雨量将达 100 毫米以上",
                "at": "2026-09-16T08:00:00+00:00",
            }

        # 订阅源来自 Redis，测试里替换掉（不需要真起 Pub/Sub）
        monkeypatch.setattr("app.core.event_bus.subscribe", fake_subscribe)

        async with client.stream(
            "GET", "/api/v1/notifications/stream", headers=auth_headers
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            # 必须禁止代理缓冲，否则 Nginx 会把 SSE 攒成一次性输出
            assert resp.headers["x-accel-buffering"] == "no"

            lines: list[str] = []
            async for line in resp.aiter_lines():
                lines.append(line)
                if len(lines) >= 4:
                    break

        body = "\n".join(lines)
        assert "connected" in body  # 连接建立后立刻回注释行
        assert "data:" in body  # 事件以 SSE 的 data 行下发
        assert "暴雨红色预警" in body


class TestPrefs:
    """通知偏好统一接口（Day 39）。"""

    async def test_默认全开(self, client, auth_headers):
        resp = await client.get("/api/v1/notifications/prefs", headers=auth_headers)
        assert resp.json()["data"] == {
            "morning_enabled": True,
            "morning_hour": 7,
            "alert_enabled": True,
            "itinerary_enabled": True,
        }

    async def test_部分更新不会覆盖其他字段(self, client, auth_headers):
        await client.put(
            "/api/v1/notifications/prefs", json={"alert_enabled": False}, headers=auth_headers
        )
        # 再改另一个开关：前一个必须保留。
        # 前端每个开关是独立保存的，全量覆盖会让快速连点丢掉设置。
        resp = await client.put(
            "/api/v1/notifications/prefs", json={"itinerary_enabled": False}, headers=auth_headers
        )
        data = resp.json()["data"]
        assert data["alert_enabled"] is False
        assert data["itinerary_enabled"] is False
        assert data["morning_enabled"] is True

    async def test_偏好持久化(self, client, auth_headers):
        await client.put(
            "/api/v1/notifications/prefs",
            json={"morning_enabled": False, "morning_hour": 8},
            headers=auth_headers,
        )
        data = (
            await client.get("/api/v1/notifications/prefs", headers=auth_headers)
        ).json()["data"]
        assert data["morning_enabled"] is False
        assert data["morning_hour"] == 8

    async def test_推送时间超出范围被拒(self, client, auth_headers):
        resp = await client.put(
            "/api/v1/notifications/prefs", json={"morning_hour": 23}, headers=auth_headers
        )
        assert resp.status_code == 422

    async def test_未登录不能读写偏好(self, client):
        assert (await client.get("/api/v1/notifications/prefs")).status_code == 401


class TestSubscriptionManagement:
    """多设备订阅管理（Day 39）。"""

    async def _subscribe(self, client, headers, endpoint: str, ua: str = "test-agent"):
        return await client.post(
            "/api/v1/notifications/subscriptions",
            json={
                "endpoint": endpoint,
                "keys": {"p256dh": "k" * 20, "auth": "a" * 20},
                "user_agent": ua,
            },
            headers=headers,
        )

    async def _list(self, client, headers) -> dict:
        resp = await client.get("/api/v1/notifications/subscriptions", headers=headers)
        return resp.json()["data"]

    async def test_列出自己的订阅(self, client, auth_headers):
        await self._subscribe(client, auth_headers, "https://push.example.com/device-1", "iPhone 15")

        data = await self._list(client, auth_headers)
        assert data["total"] == 1
        assert data["items"][0]["user_agent"] == "iPhone 15"
        assert data["items"][0]["is_active"] is True

    async def test_退订指定设备(self, client, auth_headers):
        await self._subscribe(client, auth_headers, "https://push.example.com/device-2")
        sub_id = (await self._list(client, auth_headers))["items"][0]["id"]

        resp = await client.delete(
            f"/api/v1/notifications/subscriptions/{sub_id}", headers=auth_headers
        )
        assert resp.status_code == 200
        assert (await self._list(client, auth_headers))["total"] == 0

    async def test_不能退订别人的设备(self, client, auth_headers, admin_headers):
        await self._subscribe(client, admin_headers, "https://push.example.com/admin-device")
        sub_id = (await self._list(client, admin_headers))["items"][0]["id"]

        # 别人的订阅按「不存在」处理：不泄漏这个 id 是否有效
        resp = await client.delete(
            f"/api/v1/notifications/subscriptions/{sub_id}", headers=auth_headers
        )
        assert resp.status_code == 404
        assert (await self._list(client, admin_headers))["total"] == 1
