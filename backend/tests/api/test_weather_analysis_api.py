"""时序分析接口测试（Day 42）。"""

from datetime import UTC, date, datetime

from app.models.weather import WeatherHistory
from app.services import weather_sync


def _row(loc: str, day: str, t_max: float, t_min: float, precip: float = 0.0) -> WeatherHistory:
    return WeatherHistory(
        time=datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC),
        location_code=loc,
        temperature=t_max,
        feels_like=t_min,
        precipitation=precip,
        humidity=None,
        is_forecast=False,
        raw={"daily": {}},
    )


class TestAnalysisDaily:
    async def test_未登录不能查看趋势(self, client):
        assert (await client.get("/api/v1/weather/analysis/daily")).status_code == 401

    async def test_返回日序列(self, client, db, auth_headers):
        db.add_all(
            [_row("api_a", "2026-09-01", 33.0, 25.0, 2.0), _row("api_a", "2026-09-02", 32.0, 24.0)]
        )
        await db.commit()

        resp = await client.get(
            "/api/v1/weather/analysis/daily?location=api_a", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2
        assert data["items"][0]["date"] == "2026-09-01"
        assert data["items"][0]["temp_max"] == 33.0

    async def test_天数参数越界被拒(self, client, auth_headers):
        resp = await client.get("/api/v1/weather/analysis/daily?days=9999", headers=auth_headers)
        assert resp.status_code == 422


class TestAnalysisCompare:
    async def test_未登录不能查看同比(self, client):
        assert (await client.get("/api/v1/weather/analysis/compare")).status_code == 401

    async def test_无同期数据时如实返回(self, client, auth_headers):
        resp = await client.get(
            "/api/v1/weather/analysis/compare?kind=yoy&year=2020&month=3&location=api_none",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["available"] is False
        assert data["reason"]

    async def test_非法的对比类型被拒(self, client, auth_headers):
        resp = await client.get(
            "/api/v1/weather/analysis/compare?kind=weekly", headers=auth_headers
        )
        assert resp.status_code == 422


class TestSyncArchive:
    async def test_未登录不能回补(self, client):
        resp = await client.post("/api/v1/weather/sync-archive?start=2025-09-01&end=2025-09-30")
        assert resp.status_code == 401

    async def test_日期格式错误被拒(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/weather/sync-archive?start=2025/09/01&end=2025-09-30", headers=auth_headers
        )
        assert resp.status_code == 422
        assert "YYYY-MM-DD" in resp.json()["detail"]

    async def test_结束早于开始被拒(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/weather/sync-archive?start=2025-09-30&end=2025-09-01", headers=auth_headers
        )
        assert resp.status_code == 422
        assert "不能早于" in resp.json()["detail"]

    async def test_回补后自动刷新聚合(self, client, auth_headers, monkeypatch):
        calls: dict = {}

        async def fake_backfill(start, end, location_code=None, **kw):
            calls["range"] = (start, end, location_code)
            return {"fetched": 30, "stored": 30, "location_code": location_code or "gz"}

        async def fake_refresh(since=None):
            calls["refresh"] = since
            return True

        monkeypatch.setattr(weather_sync, "backfill_archive", fake_backfill)
        monkeypatch.setattr("app.services.weather_analysis.refresh_daily_aggregate", fake_refresh)

        resp = await client.post(
            "/api/v1/weather/sync-archive?start=2025-09-01&end=2025-09-30&location=gz",
            headers=auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["stored"] == 30
        assert data["aggregate_refreshed"] is True
        assert calls["range"] == (date(2025, 9, 1), date(2025, 9, 30), "gz")
        # 回补必须触发刷新，否则数据要等下一个整点才出现在统计里
        assert calls["refresh"] == date(2025, 9, 1)


class TestAnalysisRefresh:
    async def test_未登录不能刷新(self, client):
        assert (await client.post("/api/v1/weather/analysis/refresh")).status_code == 401

    async def test_刷新成功(self, client, auth_headers, monkeypatch):
        async def fake_refresh(since=None):
            return True

        monkeypatch.setattr("app.services.weather_analysis.refresh_daily_aggregate", fake_refresh)
        resp = await client.post("/api/v1/weather/analysis/refresh", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["refreshed"] is True

    async def test_日期格式错误被拒(self, client, auth_headers):
        resp = await client.post(
            "/api/v1/weather/analysis/refresh?since=昨天", headers=auth_headers
        )
        assert resp.status_code == 422
