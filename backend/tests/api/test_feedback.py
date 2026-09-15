"""反馈接口测试：匿名提交、回复闭环、隐私隔离。

重点覆盖 Day 23 修复的两个 BUG（回归测试）：
1. **管理员回复在用户端可见**（此前前端类型缺失 + 后端漏字段）
2. **普通用户看不到他人反馈**（此前筛选条件只作用于 count，rows 漏了 where）
"""


class TestCreateFeedback:
    async def test_匿名可以提交(self, client):
        r = await client.post(
            "/api/v1/feedback", json={"content": "匿名反馈内容", "contact": "13800000000"}
        )
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["user_id"] is None  # 匿名
        assert data["status"] == "pending"

    async def test_登录提交会关联用户(self, client, auth_headers, db):
        r = await client.post(
            "/api/v1/feedback", headers=auth_headers, json={"content": "登录用户的反馈"}
        )
        assert r.status_code == 201
        assert r.json()["data"]["user_id"] is not None

    async def test_空内容被拒(self, client):
        r = await client.post("/api/v1/feedback", json={"content": ""})
        assert r.status_code == 422


class TestReplyFlow:
    """管理员回复 -> 用户端能看到（Day 23 修复的闭环）。"""

    async def test_管理员回复后用户端可见(self, client, auth_headers, admin_headers):
        # 用户提交
        created = await client.post(
            "/api/v1/feedback", headers=auth_headers, json={"content": "功能建议：希望支持离线"}
        )
        fid = created.json()["data"]["id"]

        # 管理员回复
        r = await client.put(
            f"/api/v1/feedback/{fid}",
            headers=admin_headers,
            json={"reply": "已收到，下个版本安排", "status": "resolved"},
        )
        assert r.status_code == 200

        # 用户端应能看到回复内容与回复时间
        listed = await client.get("/api/v1/feedback", headers=auth_headers)
        item = listed.json()["data"]["items"][0]
        assert item["reply"] == "已收到，下个版本安排"
        assert item["reply_at"] is not None
        assert item["status"] == "resolved"

    async def test_普通用户无权回复(self, client, auth_headers):
        created = await client.post(
            "/api/v1/feedback", headers=auth_headers, json={"content": "普通用户反馈"}
        )
        fid = created.json()["data"]["id"]

        r = await client.put(
            f"/api/v1/feedback/{fid}", headers=auth_headers, json={"reply": "我自己回复"}
        )
        assert r.status_code == 403

    async def test_未回复时reply为空(self, client, auth_headers):
        await client.post("/api/v1/feedback", headers=auth_headers, json={"content": "待处理"})
        item = (await client.get("/api/v1/feedback", headers=auth_headers)).json()["data"]["items"][
            0
        ]
        assert item["reply"] is None
        assert item["reply_at"] is None


class TestPrivacyIsolation:
    """隐私隔离：普通用户只能看到自己的反馈（Day 23 修复的越权）。"""

    async def test_普通用户看不到他人反馈(self, client, auth_headers):
        # 我提交一条
        await client.post("/api/v1/feedback", headers=auth_headers, json={"content": "我的反馈"})

        # 另一个用户提交一条
        other = {"username": "fb_other", "password": "Pass@123456"}
        await client.post("/api/v1/users/register", json=other)
        token = (await client.post("/api/v1/users/login", json=other)).json()["data"][
            "access_token"
        ]
        other_headers = {"Authorization": f"Bearer {token}"}
        await client.post("/api/v1/feedback", headers=other_headers, json={"content": "别人的反馈"})

        # 只应看到自己那条，且 total 与实际条数一致
        r = await client.get("/api/v1/feedback", headers=auth_headers)
        data = r.json()["data"]
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["content"] == "我的反馈"

    async def test_看不到匿名反馈(self, client, auth_headers):
        """匿名反馈未关联账号，登录用户不应看到。"""
        await client.post("/api/v1/feedback", json={"content": "匿名提交的"})
        r = await client.get("/api/v1/feedback", headers=auth_headers)
        assert r.json()["data"]["total"] == 0

    async def test_管理员可以看到全部(self, client, auth_headers, admin_headers):
        await client.post("/api/v1/feedback", headers=auth_headers, json={"content": "用户反馈"})
        await client.post("/api/v1/feedback", json={"content": "匿名反馈"})

        r = await client.get("/api/v1/feedback", headers=admin_headers)
        assert r.json()["data"]["total"] == 2

    async def test_他人反馈详情不可访问(self, client, auth_headers):
        created = await client.post(
            "/api/v1/feedback", headers=auth_headers, json={"content": "私有反馈"}
        )
        fid = created.json()["data"]["id"]

        other = {"username": "fb_other2", "password": "Pass@123456"}
        await client.post("/api/v1/users/register", json=other)
        token = (await client.post("/api/v1/users/login", json=other)).json()["data"][
            "access_token"
        ]

        r = await client.get(
            f"/api/v1/feedback/{fid}", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 403


class TestStatusFilter:
    async def test_按状态筛选(self, client, auth_headers, admin_headers):
        created = await client.post(
            "/api/v1/feedback", headers=auth_headers, json={"content": "会被处理"}
        )
        fid = created.json()["data"]["id"]
        await client.put(
            f"/api/v1/feedback/{fid}", headers=admin_headers, json={"status": "resolved"}
        )

        r = await client.get(
            "/api/v1/feedback", headers=auth_headers, params={"status_filter": "resolved"}
        )
        assert r.json()["data"]["total"] == 1

        r = await client.get(
            "/api/v1/feedback", headers=auth_headers, params={"status_filter": "pending"}
        )
        assert r.json()["data"]["total"] == 0


class TestAuthRequired:
    async def test_列表需要登录(self, client):
        assert (await client.get("/api/v1/feedback")).status_code == 401

    async def test_提交无需登录(self, client):
        r = await client.post("/api/v1/feedback", json={"content": "无需登录"})
        assert r.status_code == 201
