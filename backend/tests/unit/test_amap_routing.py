"""高德路线规划解析测试（驾车 / 公交 / 兜底）。

补上 amap_client 的解析层覆盖：
- 驾车：距离（米→公里）、耗时（秒→分钟）、费用估算、路书拼接
- 公交：换乘线路提取
- 兜底：无 Key / 解析失败时按直线距离估算多交通方式
"""

import httpx
import pytest

from app.services import amap_client

DRIVING_RESP = {
    "status": "1",
    "route": {
        "paths": [
            {
                "distance": "4400",
                "duration": "720",
                "tolls": "0",
                "steps": [{"instruction": "沿猎德大道向北行驶"}, {"instruction": "右转进入阅江路"}],
            }
        ]
    },
}

TRANSIT_RESP = {
    "status": "1",
    "route": {
        "transits": [
            {
                "distance": "3200",
                "duration": "1680",
                "cost": "2.0",
                "segments": [
                    {"bus": {"buslines": [{"type": "地铁", "name": "地铁3号线"}]}},
                    {"bus": {"buslines": [{"type": "公交", "name": "B7路"}]}},
                ],
            }
        ]
    },
}


@pytest.fixture
def amap_ready(monkeypatch):
    """配好 Key 并把地理编码打桩掉（聚焦路线解析本身）。"""
    monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "fake-key")

    async def fake_geocode(address, city=None):
        return {"lng": 113.3, "lat": 23.1, "formatted": address}

    monkeypatch.setattr(amap_client, "geocode", fake_geocode)


class TestDriving:
    async def test_单位换算与路书解析(self, amap_ready, respx_mock):
        respx_mock.get("https://restapi.amap.com/v3/direction/driving").mock(
            return_value=httpx.Response(200, json=DRIVING_RESP)
        )
        result = await amap_client._plan_driving_amap("A", "B", None)

        assert result is not None
        route = result["routes"][0]
        assert route["distance_km"] == 4.4  # 4400 米 -> 4.4 公里
        assert route["duration_min"] == 12  # 720 秒 -> 12 分钟
        assert route["mode"] == "驾车"
        assert "猎德大道" in route["detail"]

    async def test_费用按里程估算(self, amap_ready, respx_mock):
        respx_mock.get("https://restapi.amap.com/v3/direction/driving").mock(
            return_value=httpx.Response(200, json=DRIVING_RESP)
        )
        result = await amap_client._plan_driving_amap("A", "B", None)
        # 4.4km * 0.5 元/km + 0 过路费
        assert result["routes"][0]["cost"] == pytest.approx(2.2)

    async def test_接口失败返回None(self, amap_ready, respx_mock):
        respx_mock.get("https://restapi.amap.com/v3/direction/driving").mock(
            return_value=httpx.Response(200, json={"status": "0", "info": "DAILY_QUERY_OVER_LIMIT"})
        )
        assert await amap_client._plan_driving_amap("A", "B", None) is None

    async def test_网络异常返回None(self, amap_ready, respx_mock):
        respx_mock.get("https://restapi.amap.com/v3/direction/driving").mock(
            side_effect=httpx.ConnectError("boom")
        )
        assert await amap_client._plan_driving_amap("A", "B", None) is None

    async def test_无坐标且解析失败返回None(self, monkeypatch, respx_mock):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "fake-key")

        async def fake_geocode(address, city=None):
            return None

        monkeypatch.setattr(amap_client, "geocode", fake_geocode)
        assert await amap_client._plan_driving_amap("A", "B", None) is None


class TestTransit:
    async def test_换乘线路提取(self, amap_ready, respx_mock):
        respx_mock.get("https://restapi.amap.com/v3/direction/transit/integrated").mock(
            return_value=httpx.Response(200, json=TRANSIT_RESP)
        )
        result = await amap_client._plan_transit_amap("A", "B", None)

        route = result["routes"][0]
        assert route["mode"] == "地铁/公交"
        assert route["distance_km"] == 3.2
        assert route["duration_min"] == 28
        assert "地铁3号线" in route["detail"]

    async def test_接口失败返回None(self, amap_ready, respx_mock):
        respx_mock.get("https://restapi.amap.com/v3/direction/transit/integrated").mock(
            return_value=httpx.Response(200, json={"status": "0"})
        )
        assert await amap_client._plan_transit_amap("A", "B", None) is None


class TestPlanRouteMerge:
    async def test_驾车与公交合并后按耗时排序(self, amap_ready, respx_mock):
        respx_mock.get("https://restapi.amap.com/v3/direction/driving").mock(
            return_value=httpx.Response(200, json=DRIVING_RESP)
        )
        respx_mock.get("https://restapi.amap.com/v3/direction/transit/integrated").mock(
            return_value=httpx.Response(200, json=TRANSIT_RESP)
        )
        result = await amap_client.plan_route("A", "B")

        durations = [r["duration_min"] for r in result["routes"]]
        assert durations == sorted(durations)  # 升序
        assert len(result["routes"]) == 2

    async def test_高德全部失败时降级到兜底方案(self, amap_ready, respx_mock):
        respx_mock.get("https://restapi.amap.com/v3/direction/driving").mock(
            return_value=httpx.Response(200, json={"status": "0"})
        )
        respx_mock.get("https://restapi.amap.com/v3/direction/transit/integrated").mock(
            return_value=httpx.Response(200, json={"status": "0"})
        )
        result = await amap_client.plan_route("广州南站", "广州塔")

        # 兜底方案由本地地标 + 直线距离估算产出
        assert result["mode"] == "fallback"
        assert result["routes"]

    async def test_未配置Key时直接走兜底(self, monkeypatch):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "")
        result = await amap_client.plan_route("广州南站", "广州塔")
        assert result["mode"] == "fallback"
        assert result["routes"]

    async def test_兜底方案包含多种交通方式(self, monkeypatch):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "")
        result = await amap_client.plan_route("广州南站", "广州塔")
        modes = {r["mode"] for r in result["routes"]}
        assert len(modes) >= 2


class TestGeocode:
    async def test_无Key时查本地地标(self, monkeypatch):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "")
        r = await amap_client.geocode("广州塔")
        assert r is not None
        assert r["lng"] == pytest.approx(113.3245)

    async def test_无Key且地标未命中时用城市字典(self, monkeypatch):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "")
        r = await amap_client.geocode("广州")
        assert r is not None
        assert r["lng"] > 0

    async def test_高德地理编码解析(self, monkeypatch, respx_mock):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "fake-key")
        respx_mock.get("https://restapi.amap.com/v3/geocode/geo").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "1",
                    "geocodes": [
                        {
                            "formatted_address": "广东省广州市海珠区广州塔",
                            "location": "113.324521,23.106428",
                        }
                    ],
                },
            )
        )
        r = await amap_client.geocode("广州塔")
        assert r["lng"] == pytest.approx(113.324521)
        assert "广州塔" in r["formatted"]

    async def test_地理编码失败返回None(self, monkeypatch, respx_mock):
        monkeypatch.setattr(amap_client.settings, "AMAP_API_KEY", "fake-key")
        respx_mock.get("https://restapi.amap.com/v3/geocode/geo").mock(
            return_value=httpx.Response(200, json={"status": "0"})
        )
        # 注意：geocode 失败不会再退化查地标，直接 None
        assert await amap_client.geocode("不存在的地址") is None


class TestHaversine:
    def test_相同点距离为0(self):
        assert amap_client._haversine_km(113.3, 23.1, 113.3, 23.1) == pytest.approx(0)

    def test_广州到深圳约100公里量级(self):
        d = amap_client._haversine_km(113.2644, 23.1291, 114.0579, 22.5431)
        assert 90 < d < 120

    def test_距离对称(self):
        a = amap_client._haversine_km(113.3, 23.1, 113.4, 23.2)
        b = amap_client._haversine_km(113.4, 23.2, 113.3, 23.1)
        assert a == pytest.approx(b)
