"""行程接口测试：CRUD + 编辑 + 用户间数据隔离。

覆盖 Day 22（补上行程编辑）与数据隔离两条关键行为：
**A 用户绝不能看到/改到 B 用户的行程**。
"""


async def _create(client, headers, **overrides) -> dict:
    payload = {
        "title": "白云山爬山",
        "date": "2026-09-20",
        "start_time": "09:00",
        "location": "白云山",
        "activity": "爬山",
        "note": "记得带水",
    }
    payload.update(overrides)
    r = await client.post("/api/v1/itinerary", headers=headers, json=payload)
    assert r.status_code == 201
    return r.json()["data"]


class TestCreate:
    async def test_创建成功(self, client, auth_headers):
        item = await _create(client, auth_headers)
        assert item["title"] == "白云山爬山"
        assert item["date"] == "2026-09-20"
        assert item["id"] > 0

    async def test_日期格式非法报错(self, client, auth_headers):
        r = await client.post(
            "/api/v1/itinerary",
            headers=auth_headers,
            json={"title": "测试", "date": "2026/09/20"},
        )
        assert r.status_code == 400

    async def test_缺少标题被拒(self, client, auth_headers):
        r = await client.post(
            "/api/v1/itinerary", headers=auth_headers, json={"date": "2026-09-20"}
        )
        assert r.status_code == 422

    async def test_未登录不能创建(self, client):
        r = await client.post("/api/v1/itinerary", json={"title": "x", "date": "2026-09-20"})
        assert r.status_code == 401


class TestList:
    async def test_只返回本人行程(self, client, auth_headers):
        await _create(client, auth_headers, title="我的行程A")
        r = await client.get("/api/v1/itinerary", headers=auth_headers)
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["title"] == "我的行程A"

    async def test_按日期过滤(self, client, auth_headers):
        await _create(client, auth_headers, title="A", date="2026-09-20")
        await _create(client, auth_headers, title="B", date="2026-09-25")

        r = await client.get(
            "/api/v1/itinerary", headers=auth_headers, params={"date": "2026-09-25"}
        )
        items = r.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["title"] == "B"

    async def test_未登录拒绝(self, client):
        assert (await client.get("/api/v1/itinerary")).status_code == 401


class TestUpdate:
    """编辑功能（此前接口只有增删查，用户无法修改已建行程）。"""

    async def test_编辑标题(self, client, auth_headers):
        item = await _create(client, auth_headers)
        r = await client.put(
            f"/api/v1/itinerary/{item['id']}",
            headers=auth_headers,
            json={"title": "白云山爬山（已改期）"},
        )
        assert r.status_code == 200
        assert r.json()["data"]["title"] == "白云山爬山（已改期）"

    async def test_只更新传入字段(self, client, auth_headers):
        item = await _create(client, auth_headers)
        await client.put(
            f"/api/v1/itinerary/{item['id']}", headers=auth_headers, json={"title": "新标题"}
        )
        r = await client.get("/api/v1/itinerary", headers=auth_headers)
        updated = r.json()["data"]["items"][0]
        assert updated["title"] == "新标题"
        assert updated["location"] == "白云山"  # 未传的字段保持不变

    async def test_空请求体报错(self, client, auth_headers):
        item = await _create(client, auth_headers)
        r = await client.put(f"/api/v1/itinerary/{item['id']}", headers=auth_headers, json={})
        assert r.status_code == 400

    async def test_不存在返回404(self, client, auth_headers):
        r = await client.put("/api/v1/itinerary/999999", headers=auth_headers, json={"title": "x"})
        assert r.status_code == 404

    async def test_改日期格式非法报错(self, client, auth_headers):
        item = await _create(client, auth_headers)
        r = await client.put(
            f"/api/v1/itinerary/{item['id']}",
            headers=auth_headers,
            json={"date": "bad-date"},
        )
        assert r.status_code == 400


class TestDelete:
    async def test_删除成功(self, client, auth_headers):
        item = await _create(client, auth_headers)
        r = await client.delete(f"/api/v1/itinerary/{item['id']}", headers=auth_headers)
        assert r.status_code == 200

        r = await client.get("/api/v1/itinerary", headers=auth_headers)
        assert r.json()["data"]["items"] == []

    async def test_重复删除返回404(self, client, auth_headers):
        item = await _create(client, auth_headers)
        await client.delete(f"/api/v1/itinerary/{item['id']}", headers=auth_headers)
        r = await client.delete(f"/api/v1/itinerary/{item['id']}", headers=auth_headers)
        assert r.status_code == 404


class TestIsolation:
    """多租户隔离：另一个用户不得触碰他人行程。"""

    async def test_他人不能删除我的行程(self, client, auth_headers):
        item = await _create(client, auth_headers)

        # 注册另一个用户
        other = {"username": "other_user", "password": "Pass@123456"}
        await client.post("/api/v1/users/register", json=other)
        token = (await client.post("/api/v1/users/login", json=other)).json()["data"][
            "access_token"
        ]
        other_headers = {"Authorization": f"Bearer {token}"}

        # 他看不到我的行程
        r = await client.get("/api/v1/itinerary", headers=other_headers)
        assert r.json()["data"]["items"] == []

        # 他也删不掉我的行程
        r = await client.delete(f"/api/v1/itinerary/{item['id']}", headers=other_headers)
        assert r.status_code == 404  # 不暴露"存在但不属于你"

        # 我的行程仍然完好
        r = await client.get("/api/v1/itinerary", headers=auth_headers)
        assert len(r.json()["data"]["items"]) == 1

    async def test_他人不能修改我的行程(self, client, auth_headers):
        item = await _create(client, auth_headers)

        other = {"username": "other_user2", "password": "Pass@123456"}
        await client.post("/api/v1/users/register", json=other)
        token = (await client.post("/api/v1/users/login", json=other)).json()["data"][
            "access_token"
        ]

        r = await client.put(
            f"/api/v1/itinerary/{item['id']}",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "恶意修改"},
        )
        assert r.status_code == 404

        r = await client.get("/api/v1/itinerary", headers=auth_headers)
        assert r.json()["data"]["items"][0]["title"] == "白云山爬山"


class TestAuthRequired:
    async def test_全部写操作都需要登录(self, client):
        assert (await client.post("/api/v1/itinerary", json={})).status_code == 401
        assert (await client.put("/api/v1/itinerary/1", json={})).status_code == 401
        assert (await client.delete("/api/v1/itinerary/1")).status_code == 401
