"""鉴权接口测试：注册 / 登录 / 鉴权边界。

项目的响应约定（重要，测试要按这个断言）：
- 业务错误用**真实 HTTP 状态码**（重复用户名 409、登录失败 401、未鉴权 401）
- 成功响应统一为 `{code: 0, message, data}` 结构
"""

from tests.conftest import USER_CRED


class TestRegister:
    async def test_注册成功(self, client):
        r = await client.post(
            "/api/v1/users/register",
            json={"username": "newbie", "password": "Pass@123456"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["code"] == 0
        assert body["data"]["username"] == "newbie"

    async def test_重复用户名返回409(self, client):
        payload = {"username": "dupuser", "password": "Pass@123456"}
        first = await client.post("/api/v1/users/register", json=payload)
        assert first.status_code == 201

        second = await client.post("/api/v1/users/register", json=payload)
        assert second.status_code == 409

    async def test_密码过短被拒(self, client):
        r = await client.post(
            "/api/v1/users/register", json={"username": "shortpwd", "password": "123"}
        )
        assert r.status_code == 422


class TestLogin:
    async def test_登录成功返回token与用户信息(self, client):
        await client.post("/api/v1/users/register", json=USER_CRED)
        r = await client.post("/api/v1/users/login", json=USER_CRED)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["access_token"]
        assert data["user"]["username"] == USER_CRED["username"]
        # 密码哈希绝不能出现在响应里
        assert "password" not in data["user"]

    async def test_密码错误返回401(self, client):
        await client.post("/api/v1/users/register", json=USER_CRED)
        r = await client.post(
            "/api/v1/users/login",
            json={"username": USER_CRED["username"], "password": "wrong-password"},
        )
        assert r.status_code == 401

    async def test_用户不存在返回401(self, client):
        r = await client.post(
            "/api/v1/users/login", json={"username": "ghost", "password": "Pass@123456"}
        )
        assert r.status_code == 401


class TestAuthBoundary:
    """鉴权边界：受保护接口必须拦住匿名访问。"""

    async def test_无token访问me返回401(self, client):
        r = await client.get("/api/v1/users/me")
        assert r.status_code == 401

    async def test_伪造token返回401(self, client):
        r = await client.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer fake.token.value"}
        )
        assert r.status_code == 401

    async def test_携带有效token可访问me(self, client, auth_headers):
        r = await client.get("/api/v1/users/me", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["data"]["username"] == USER_CRED["username"]

    async def test_token格式错误返回401(self, client):
        """缺少 Bearer 前缀应被拒绝。"""
        r = await client.get("/api/v1/users/me", headers={"Authorization": "not-a-bearer"})
        assert r.status_code == 401


class TestUserList:
    async def test_需要鉴权(self, client):
        assert (await client.get("/api/v1/users")).status_code == 401

    async def test_分页结构正确(self, client, auth_headers):
        r = await client.get("/api/v1/users", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert {"items", "total", "page", "page_size"} <= set(data)

    async def test_密码哈希不外泄(self, client, auth_headers):
        r = await client.get("/api/v1/users", headers=auth_headers)
        for item in r.json()["data"]["items"]:
            assert "password_hash" not in item
            assert "password" not in item
