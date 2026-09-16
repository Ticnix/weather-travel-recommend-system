"""用户资料接口测试（Day 37）。

重点是**权限**：普通用户改自己的资料可以，但
- 不能改别人的
- 更不能碰 role / is_active —— 否则任何登录用户都能把自己变成管理员

这一组用例是修完提权漏洞后补的回归防线。
"""

from app.models.user import User


async def _me(client, headers) -> dict:
    resp = await client.get("/api/v1/users/me", headers=headers)
    return resp.json()["data"]


class TestUpdateProfile:
    async def test_可以修改自己的体质偏好(self, client, auth_headers):
        me = await _me(client, auth_headers)
        resp = await client.put(
            f"/api/v1/users/{me['id']}", json={"body_preference": "cold"}, headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["body_preference"] == "cold"

    async def test_体质偏好只接受约定取值(self, client, auth_headers):
        me = await _me(client, auth_headers)
        resp = await client.put(
            f"/api/v1/users/{me['id']}",
            json={"body_preference": "随便填的"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_普通用户不能把自己改成管理员(self, client, auth_headers):
        me = await _me(client, auth_headers)
        resp = await client.put(
            f"/api/v1/users/{me['id']}", json={"role": "admin"}, headers=auth_headers
        )
        assert resp.status_code == 403
        assert "role" in resp.json()["detail"]

    async def test_普通用户不能修改他人资料(self, client, db, auth_headers):
        other = User(username="someone_else", password_hash="x")
        db.add(other)
        await db.commit()

        resp = await client.put(
            f"/api/v1/users/{other.id}", json={"nickname": "hacked"}, headers=auth_headers
        )
        assert resp.status_code == 403

    async def test_管理员可以修改他人角色(self, client, db, admin_headers):
        user = User(username="promote_me", password_hash="x")
        db.add(user)
        await db.commit()

        resp = await client.put(
            f"/api/v1/users/{user.id}", json={"role": "admin"}, headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "admin"

    async def test_未登录不能修改资料(self, client):
        resp = await client.put("/api/v1/users/1", json={"nickname": "x"})
        assert resp.status_code == 401
