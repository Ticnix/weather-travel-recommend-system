"""地点服务单元测试：内置地标、输入联想、坐标直传。

覆盖 Day 14（地点联想）相关逻辑，重点验证「坐标直传会跳过地理编码」——
这是当时修复"手输地名解析失败就报错"的关键机制。
"""

import httpx
import pytest

from app.services import amap_client


class TestLandmarks:
    """内置广州地标表。"""

    def test_别名词条只保留一个(self):
        """「广州塔」与「小蛮腰」坐标相同，输出时应去重。"""
        items = amap_client.list_landmarks()
        names = [i["name"] for i in items]
        assert "广州塔" in names
        assert "小蛮腰" not in names

    def test_返回结构字段完整(self):
        items = amap_client.list_landmarks()
        assert items
        assert all({"name", "lng", "lat"} <= set(i) for i in items)

    def test_精确匹配(self):
        r = amap_client._lookup_landmark("广州塔")
        assert r is not None
        assert r["lng"] == pytest.approx(113.3245)

    def test_包含匹配(self):
        """「广州塔西门」应命中「广州塔」。"""
        r = amap_client._lookup_landmark("广州塔西门")
        assert r is not None
        assert r["formatted"] == "广州塔"

    def test_未命中返回None(self):
        assert amap_client._lookup_landmark("不存在的火星基地") is None


class TestSuggestPlaces:
    """输入联想（高德 assistant/inputtips + 无 Key 降级）。"""

    async def test_无Key时降级为本地地标匹配(self, monkeypatch):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "")
        r = await amap_client.suggest_places("广州塔")
        assert r
        assert r[0]["name"] == "广州塔"

    async def test_空关键词返回空列表(self, monkeypatch):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "fake-key")
        assert await amap_client.suggest_places("   ") == []

    async def test_解析结果并过滤无坐标条目(self, monkeypatch, respx_mock):
        """行政区、公交线等条目没有坐标，不能用于路线规划，必须过滤掉。"""
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "fake-key")
        respx_mock.get("https://restapi.amap.com/v3/assistant/inputtips").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "1",
                    "tips": [
                        {
                            "name": "猎德大桥",
                            "district": "广东省广州市海珠区",
                            "location": "113.333970,23.109528",
                        },
                        {"name": "天河区", "district": "广东省广州市天河区", "location": []},
                    ],
                },
            )
        )
        r = await amap_client.suggest_places("猎德")
        assert len(r) == 1
        assert r[0]["name"] == "猎德大桥"
        assert r[0]["lng"] == pytest.approx(113.33397)

    async def test_高德返回失败状态时返回空(self, monkeypatch, respx_mock):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "fake-key")
        respx_mock.get("https://restapi.amap.com/v3/assistant/inputtips").mock(
            return_value=httpx.Response(
                200, json={"status": "0", "info": "INVALID_USER_KEY"}
            )
        )
        assert await amap_client.suggest_places("猎德") == []

    async def test_网络异常时不抛错(self, monkeypatch, respx_mock):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "fake-key")
        respx_mock.get("https://restapi.amap.com/v3/assistant/inputtips").mock(
            side_effect=httpx.ConnectError("boom")
        )
        assert await amap_client.suggest_places("猎德") == []


class TestPlanRouteWithCoords:
    """坐标直传：这是"选点不再报错"的核心机制。"""

    async def test_坐标直传时不调用地理编码(self, monkeypatch):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "fake-key")
        calls = {"geocode": 0, "driving_point": None}

        async def fake_geocode(address, city=None):
            calls["geocode"] += 1
            return None  # 故意返回 None，模拟"地名解析不出来"

        async def fake_driving(origin, destination, city, o_point=None, d_point=None):
            calls["driving_point"] = (o_point, d_point)
            return {
                "routes": [
                    {
                        "mode": "驾车",
                        "duration_min": 10,
                        "distance_km": 5.0,
                        "cost": 3.0,
                        "detail": "沿江行驶",
                    }
                ]
            }

        async def fake_transit(*args, **kwargs):
            return None

        monkeypatch.setattr(amap_client, "geocode", fake_geocode)
        monkeypatch.setattr(amap_client, "_plan_driving_amap", fake_driving)
        monkeypatch.setattr(amap_client, "_plan_transit_amap", fake_transit)

        result = await amap_client.plan_route(
            "乱写的名字",
            "也乱写",
            origin_point={"lng": 113.3, "lat": 23.1},
            destination_point={"lng": 113.4, "lat": 23.2},
        )

        assert calls["geocode"] == 0  # 全程没有走地理编码
        assert calls["driving_point"] == (
            {"lng": 113.3, "lat": 23.1},
            {"lng": 113.4, "lat": 23.2},
        )
        assert result["routes"]

    async def test_无坐标时回退到地理编码(self, monkeypatch, respx_mock):
        """没传坐标（用户直接手输地名）时必须走地理编码。

        直接测 `_plan_driving_amap`：它在内部调用 geocode，
        比在 plan_route 层断言更贴近真实调用链。
        """
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "fake-key")
        calls = {"geocode": 0}

        async def fake_geocode(address, city=None):
            calls["geocode"] += 1
            return {"lng": 113.3, "lat": 23.1, "formatted": address}

        monkeypatch.setattr(amap_client, "geocode", fake_geocode)
        # 高德返回失败状态 -> 函数安全返回 None（同时证明 geocode 确实被调用了）
        respx_mock.get("https://restapi.amap.com/v3/direction/driving").mock(
            return_value=httpx.Response(200, json={"status": "0"})
        )

        result = await amap_client._plan_driving_amap("广州南站", "广州塔", None)
        assert result is None
        assert calls["geocode"] == 2  # 起点与终点各解析一次
