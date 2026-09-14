"""首页仪表盘接口测试。

首页把「天气 + 提醒 + 穿搭 + 行程」聚合在一个接口里，
因此涉及外部天气 API 与 RAG，这里全部 Mock——测试不联网、不需要 Key。
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services import home_service
from skills.outfit_recommend.scripts import outfit_engine


def _fake_bundle(desc: str = "雷阵雨", tmax: float = 33.0, tmin: float = 25.0, precip: float = 6.5):
    """构造假天气数据（字段结构对齐真实的 WeatherBundle）。"""
    today = date.today()
    daily = [
        SimpleNamespace(
            date=(today + timedelta(days=i)).isoformat(),
            weather_desc=desc if i == 0 else "多云",
            temp_min=tmin,
            temp_max=tmax,
            precipitation_sum=precip if i == 0 else 0.0,
        )
        for i in range(7)
    ]
    return SimpleNamespace(
        current=SimpleNamespace(
            weather_desc=desc,
            temperature=tmax - 1,
            feels_like=tmax + 2,
            humidity=70.0,
            precipitation=precip,
        ),
        daily=daily,
        alerts=[],
    )


@pytest.fixture(autouse=True)
def _mock_external(monkeypatch):
    """切断首页链路里的所有外部依赖（天气 API + RAG 向量检索）。"""

    async def fake_fetch_weather(city=None, *args, **kwargs):
        return _fake_bundle()

    async def fake_rag_search(*args, **kwargs):
        return []

    # home_service 与 outfit_engine 各自 import 了 fetch_weather，需要分别打桩
    monkeypatch.setattr(home_service, "fetch_weather", fake_fetch_weather)
    monkeypatch.setattr(outfit_engine, "fetch_weather", fake_fetch_weather)
    monkeypatch.setattr(outfit_engine.rag_service, "search", fake_rag_search)


async def _add_itinerary(client, headers, **overrides) -> dict:
    today = date.today()
    payload = {
        "title": "珠江夜游",
        "date": today.isoformat(),
        "start_time": "09:00",
        "location": "珠江",
    }
    payload.update(overrides)
    r = await client.post("/api/v1/itinerary", headers=headers, json=payload)
    assert r.status_code == 201
    return r.json()["data"]


class TestAnonymous:
    """未登录：只给天气与通用建议，不含行程。"""

    async def test_可匿名访问(self, client):
        r = await client.get("/api/v1/home/dashboard")
        assert r.status_code == 200

    async def test_返回天气与提示(self, client):
        data = (await client.get("/api/v1/home/dashboard")).json()["data"]
        assert data["weather"]["desc"] == "雷阵雨"
        assert data["weather"]["temp_max"] == 33.0
        assert data["tips"]
        assert data["logged_in"] is False

    async def test_未登录不含行程(self, client):
        data = (await client.get("/api/v1/home/dashboard")).json()["data"]
        assert data["itinerary"]["total"] == 0
        assert data["itinerary"]["upcoming"] == []

    async def test_返回穿搭建议(self, client):
        data = (await client.get("/api/v1/home/dashboard")).json()["data"]
        assert data["outfit"] is not None
        assert data["outfit"]["suggestion"]

    async def test_结构字段完整(self, client):
        data = (await client.get("/api/v1/home/dashboard")).json()["data"]
        assert {"city", "date", "weather", "tips", "outfit", "itinerary", "logged_in"} <= set(data)


class TestLoggedIn:
    """登录后：额外返回行程及其天气提醒。"""

    async def test_返回行程并附天气提示(self, client, auth_headers):
        await _add_itinerary(client, auth_headers)

        data = (await client.get("/api/v1/home/dashboard", headers=auth_headers)).json()["data"]
        assert data["logged_in"] is True
        assert data["itinerary"]["total"] == 1

        item = data["itinerary"]["upcoming"][0]
        assert item["title"] == "珠江夜游"
        assert item["weather_hint"]  # 必须带上一句天气提示
        assert "雷阵雨" in item["weather_hint"]

    async def test_只返回未来7天内的行程(self, client, auth_headers):
        today = date.today()
        await _add_itinerary(client, auth_headers, title="今天", date=today.isoformat())
        await _add_itinerary(
            client, auth_headers, title="三天后", date=(today + timedelta(days=3)).isoformat()
        )
        await _add_itinerary(
            client, auth_headers, title="很久以后", date=(today + timedelta(days=30)).isoformat()
        )

        data = (await client.get("/api/v1/home/dashboard", headers=auth_headers)).json()["data"]
        titles = [i["title"] for i in data["itinerary"]["upcoming"]]
        assert "今天" in titles
        assert "三天后" in titles
        assert "很久以后" not in titles

    async def test_过去的行程不展示(self, client, auth_headers):
        today = date.today()
        await _add_itinerary(
            client, auth_headers, title="昨天", date=(today - timedelta(days=1)).isoformat()
        )
        data = (await client.get("/api/v1/home/dashboard", headers=auth_headers)).json()["data"]
        assert data["itinerary"]["total"] == 0

    async def test_行程跨城市解析对应城市天气(self, client, auth_headers):
        """上海行程应解析出城市「上海」，而不是一律用默认城市。"""
        today = date.today()
        await _add_itinerary(
            client,
            auth_headers,
            title="迪士尼一日游",
            date=today.isoformat(),
            location="上海迪士尼",
        )
        data = (await client.get("/api/v1/home/dashboard", headers=auth_headers)).json()["data"]
        assert data["itinerary"]["upcoming"][0]["city"] == "上海"


class TestDegradation:
    """降级：天气服务不可用时首页也不能整体报错。"""

    async def test_天气服务异常仍返回200(self, client, monkeypatch):
        async def boom(*args, **kwargs):
            raise RuntimeError("天气服务挂了")

        monkeypatch.setattr(home_service, "fetch_weather", boom)
        monkeypatch.setattr(outfit_engine, "fetch_weather", boom)

        r = await client.get("/api/v1/home/dashboard")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["weather"] == {}  # 天气为空
        assert data["tips"] == []

    async def test_支持指定城市(self, client):
        r = await client.get("/api/v1/home/dashboard", params={"city": "上海"})
        assert r.json()["data"]["city"] == "上海"
