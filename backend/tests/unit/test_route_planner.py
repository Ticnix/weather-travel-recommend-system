"""出行规划 Skill 编排测试。

`plan_structured` 是"出行推荐"的核心编排：拿到多套路线 → 结合当天天气
→ 三维评分 → 排序输出。这里把外部依赖（高德、天气）打桩，
验证**编排逻辑**本身（评分融合、排序、天气提示、异常兜底）。
"""

from types import SimpleNamespace
from typing import ClassVar

import pytest

from skills.travel_planning.scripts import route_planner as rp


def _route(mode: str, duration: int, distance: float, cost: float) -> dict:
    return {
        "mode": mode,
        "duration_min": duration,
        "distance_km": distance,
        "cost": cost,
        "detail": f"{mode}路线详情",
    }


def _weather(desc: str = "晴", tmin: float = 22.0, tmax: float = 28.0, precip: float = 0.0):
    return SimpleNamespace(
        current=SimpleNamespace(weather_desc=desc, temperature=tmax - 1),
        daily=[
            SimpleNamespace(
                date="2026-09-14",
                weather_desc=desc,
                temp_min=tmin,
                temp_max=tmax,
                precipitation_sum=precip,
            )
        ],
        alerts=[],
    )


@pytest.fixture
def patch_deps(monkeypatch):
    """打桩外部依赖，返回一个可调整行为的控制器。"""

    class Ctl:
        # ClassVar：这些都是「测试控制器」的类级配置而非实例属性，
        # 标注后既语义清晰，也避免 lint 把它当成可变默认值
        routes: ClassVar[list] = [
            _route("驾车", 20, 8.0, 6.0),
            _route("地铁/公交", 35, 7.0, 2.0),
            _route("骑行", 50, 7.5, 0.0),
        ]
        weather: ClassVar[dict] = _weather()
        weather_error: ClassVar[bool] = False
        route_error: ClassVar[str | None] = None

    async def fake_plan_route(
        origin, destination, city=None, origin_point=None, destination_point=None
    ):
        if Ctl.route_error:
            return {
                "origin": origin,
                "destination": destination,
                "routes": [],
                "error": Ctl.route_error,
            }
        return {
            "origin": origin,
            "destination": destination,
            "mode": "driving",
            "routes": Ctl.routes,
        }

    async def fake_fetch_weather(city=None):
        if Ctl.weather_error:
            raise RuntimeError("天气服务挂了")
        return Ctl.weather

    monkeypatch.setattr(rp.amap_client, "plan_route", fake_plan_route)
    monkeypatch.setattr(rp, "fetch_weather", fake_fetch_weather)
    return Ctl


class TestPlanStructured:
    async def test_返回结构与字段完整(self, patch_deps):
        data = await rp.plan_structured("广州南站", "广州塔")

        assert data["origin"] == "广州南站"
        assert data["destination"] == "广州塔"
        assert len(data["routes"]) == 3
        for r in data["routes"]:
            assert {
                "mode",
                "duration_min",
                "distance_km",
                "cost",
                "time_score",
                "cost_score",
                "weather_score",
                "total_score",
            } <= set(r)

    async def test_按综合评分降序排序(self, patch_deps):
        data = await rp.plan_structured("A", "B")
        scores = [r["total_score"] for r in data["routes"]]
        assert scores == sorted(scores, reverse=True)

    async def test_评分融合时间与费用(self, patch_deps):
        """综合评分 = 0.4*时间 + 0.3*费用 + 0.3*天气。

        雨天时各方案天气分相同，排序由时间/费用决定：
        - 驾车 20min/6元 → 0.4*0.6 + 0.3*0    = 0.24
        - 公交 35min/2元 → 0.4*0.3 + 0.3*0.667 = 0.32
        - 骑行 50min/0元 → 0.4*0   + 0.3*1     = 0.30
        因此最便宜省心的公交胜出——说明**费用权重确实在起作用**，
        而不是单纯按耗时排序。
        """
        patch_deps.weather = _weather(desc="中雨", precip=15.0)
        data = await rp.plan_structured("A", "B")

        assert data["routes"][0]["mode"] == "地铁/公交"
        assert data["routes"][-1]["mode"] == "驾车"

    async def test_天气信息带入结果(self, patch_deps):
        patch_deps.weather = _weather(desc="雷阵雨", tmin=25, tmax=33, precip=6.5)
        data = await rp.plan_structured("A", "B")

        assert data["weather"]["desc"] == "雷阵雨"
        assert data["weather"]["temp_max"] == 33
        assert data["weather"]["precip"] == 6.5

    async def test_评分归一化到0到1(self, patch_deps):
        data = await rp.plan_structured("A", "B")
        for r in data["routes"]:
            for key in ("time_score", "cost_score", "weather_score", "total_score"):
                assert 0.0 <= r[key] <= 1.0

    async def test_免费方案费用分为满分(self, patch_deps):
        data = await rp.plan_structured("A", "B")
        cycling = next(r for r in data["routes"] if r["mode"] == "骑行")
        assert cycling["cost_score"] == 1.0


class TestPlanStructuredErrors:
    async def test_缺少起终点返回错误(self, patch_deps):
        data = await rp.plan_structured("", "广州塔")
        assert data["error"]
        # 参数校验失败时直接返回错误，不带 routes 字段
        assert data.get("routes", []) == []

    async def test_无可用路线返回错误(self, patch_deps):
        patch_deps.route_error = "无法解析起终点坐标"
        data = await rp.plan_structured("乱写", "也乱写")
        assert "无法解析" in data["error"]
        assert data["routes"] == []

    async def test_天气服务异常不影响出方案(self, patch_deps):
        """天气只是评分因子，挂了也要能给出路线。"""
        patch_deps.weather_error = True
        data = await rp.plan_structured("A", "B")

        assert len(data["routes"]) == 3
        assert data["weather"]["desc"] == ""  # 天气降级为空

    async def test_坐标参数透传给路线规划(self, monkeypatch):
        captured = {}

        async def fake_plan_route(
            origin, destination, city=None, origin_point=None, destination_point=None
        ):
            captured["o"] = origin_point
            captured["d"] = destination_point
            return {
                "origin": origin,
                "destination": destination,
                "routes": [_route("驾车", 10, 5, 1)],
            }

        async def fake_fetch_weather(city=None):
            return _weather()

        monkeypatch.setattr(rp.amap_client, "plan_route", fake_plan_route)
        monkeypatch.setattr(rp, "fetch_weather", fake_fetch_weather)

        await rp.plan_structured(
            "A",
            "B",
            origin_point={"lng": 113.3, "lat": 23.1},
            destination_point={"lng": 113.4, "lat": 23.2},
        )
        assert captured["o"] == {"lng": 113.3, "lat": 23.1}
        assert captured["d"] == {"lng": 113.4, "lat": 23.2}


class TestRunText:
    """run() 输出给 LLM 的结构化文本。"""

    async def test_正常输出包含方案与天气(self, patch_deps):
        text = await rp.run("广州南站", "广州塔")
        assert "广州南站" in text
        assert "广州塔" in text
        assert "驾车" in text
        assert "综合评分" in text

    async def test_雨天输出安全提示(self, patch_deps):
        patch_deps.weather = _weather(desc="雷阵雨", precip=12.0)
        text = await rp.run("A", "B")
        assert "天气提示" in text or "雨" in text

    async def test_失败时返回错误文本(self, patch_deps):
        patch_deps.route_error = "无法解析起终点坐标"
        text = await rp.run("乱写", "也乱写")
        assert "无法解析" in text
