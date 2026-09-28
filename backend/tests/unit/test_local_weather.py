"""区级天气测试。

覆盖两类真实踩过的坑：
1. 位置解析要能退化——用户手动选的区没有收录坐标时，必须如实降级为"市中心精度"，
   而不是假装自己取到了区级数据。
2. 上游偶发失败要重试——实测同一批请求里会零散抛 `httpx.ConnectError`（str 还是空的），
   单次失败就会让用户看到"当地天气没取到"。
"""

import httpx
import pytest

from app.services import local_weather_service as svc


class TestResolve:
    async def test_简称也能解析到区(self):
        loc = await svc.resolve(district="南沙")
        assert loc.district == "南沙区"
        assert loc.city == "广州"
        assert loc.precision == "district"
        assert loc.source == "manual"
        # 南沙的区中心（纬度比越秀低约 0.33 度）
        assert 22.7 < loc.lat < 22.9

    async def test_未收录坐标的区降级为市中心(self):
        # 「越秀」之外，深圳的区在坐标表里没收录：必须降级并如实标注
        loc = await svc.resolve(district="福田区")
        assert loc.city == "深圳"
        assert loc.district is None
        assert loc.precision == "city"

    async def test_什么都不给时用默认城市中心(self):
        loc = await svc.resolve()
        assert loc.precision == "city"
        assert loc.district is None


class TestFetchRetry:
    async def test_第一次失败第二次成功(self, monkeypatch):
        calls = {"n": 0}

        async def flaky(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                # 上游偶发连不上时抛的就是它，而且 str() 为空
                raise httpx.ConnectError("")
            return "bundle"

        monkeypatch.setattr(svc.weather_client, "fetch", flaky)
        loc = await svc.resolve(district="南沙区")

        assert await svc._fetch_with_retry(loc) == "bundle"
        assert calls["n"] == 2

    async def test_连续失败会把异常抛给调用方(self, monkeypatch):
        async def always_fail(*args, **kwargs):
            raise httpx.ConnectError("")

        monkeypatch.setattr(svc.weather_client, "fetch", always_fail)
        loc = await svc.resolve(district="南沙区")

        with pytest.raises(httpx.ConnectError):
            await svc._fetch_with_retry(loc, attempts=2)
