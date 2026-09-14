"""和风天气客户端测试。

和风是当前的生产数据源，其解析层一旦出错会直接影响首页、推荐、提醒全线。
这里用真实结构的响应样例验证解析，并覆盖三类异常：
**没配 Key / 业务错误码 / 预警接口挂掉（不能影响主流程）**。
"""

import httpx
import pytest

from app.services import qweather_client as qw

# 和风 /weather/now 的真实结构
NOW_SAMPLE = {
    "code": "200",
    "now": {
        "obsTime": "2026-09-14T13:48+08:00",
        "temp": "30",
        "feelsLike": "31",
        "icon": "104",
        "text": "阴",
        "wind360": "0",
        "windDir": "北风",
        "windScale": "6",
        "windSpeed": "44",
        "humidity": "72",
        "precip": "2.9",
        "pressure": "1006",
        "vis": "30",
    },
}

# 和风 /weather/7d 的真实结构
DAILY_SAMPLE = {
    "code": "200",
    "daily": [
        {
            "fxDate": "2026-09-14",
            "sunrise": "06:14",
            "sunset": "18:33",
            "tempMax": "33",
            "tempMin": "25",
            "iconDay": "302",
            "textDay": "雷阵雨",
            "windSpeedDay": "12",
            "windScaleDay": "1-3",
            "precip": "6.5",
        },
        {
            "fxDate": "2026-09-15",
            "tempMax": "32",
            "tempMin": "25",
            "iconDay": "305",
            "textDay": "小雨",
        },
    ],
}


class TestResolveLocation:
    """城市名 → 和风 LocationID。"""

    def test_中文城市名解析为LocationID(self):
        client = qw.QWeatherClient(api_key="k")
        loc = client._resolve_location("广州")
        assert loc.isdigit()

    def test_纯数字直接作为LocationID(self):
        client = qw.QWeatherClient(api_key="k")
        assert client._resolve_location("101280101") == "101280101"

    def test_空值走默认Location(self):
        client = qw.QWeatherClient(api_key="k")
        assert client._resolve_location(None) == qw.settings.QWEATHER_DEFAULT_LOCATION

    def test_无法识别时原样返回(self):
        """未命中城市字典时把入参透传（和风也支持 lon,lat 格式）。"""
        client = qw.QWeatherClient(api_key="k")
        assert client._resolve_location("113.26,23.13") == "113.26,23.13"


class TestParseCurrent:
    def test_解析实时天气字段(self):
        c = qw.QWeatherClient._parse_current(NOW_SAMPLE["now"])
        assert c.temperature == 30.0
        assert c.feels_like == 31.0
        assert c.humidity == 72.0
        assert c.precipitation == 2.9
        assert c.wind_direction == "北风"

    def test_图标码转为中文描述(self):
        c = qw.QWeatherClient._parse_current(NOW_SAMPLE["now"])
        # icon 104 -> 阴
        assert c.weather_desc == "阴"

    def test_时间解析为带时区时间(self):
        c = qw.QWeatherClient._parse_current(NOW_SAMPLE["now"])
        assert c.time.year == 2026
        assert c.time.tzinfo is not None

    def test_缺省字段不抛异常(self):
        """和风在部分字段缺失时会返回 '--' 或直接没有该键。"""
        c = qw.QWeatherClient._parse_current({"icon": "100"})
        assert c.temperature is None
        assert c.weather_desc == "晴"

    @pytest.mark.parametrize("raw_icon", ["104", 104])
    def test_图标码兼容字符串与整数(self, raw_icon):
        c = qw.QWeatherClient._parse_current({"icon": raw_icon})
        assert c.weather_desc == "阴"


class TestParseDaily:
    def test_解析多天预报(self):
        days = qw.QWeatherClient._parse_daily(DAILY_SAMPLE["daily"])
        assert len(days) == 2
        assert days[0].date == "2026-09-14"
        assert days[0].temp_max == 33.0
        assert days[0].temp_min == 25.0
        assert days[0].weather_desc == "雷阵雨"

    def test_日出日落解析(self):
        days = qw.QWeatherClient._parse_daily(DAILY_SAMPLE["daily"])
        assert days[0].sunrise == "06:14"
        assert days[0].sunset == "18:33"

    def test_空列表返回空(self):
        assert qw.QWeatherClient._parse_daily([]) == []

    def test_缺字段容错(self):
        days = qw.QWeatherClient._parse_daily(DAILY_SAMPLE["daily"][1:])
        assert days[0].precipitation_sum is None


class TestGetErrors:
    """_get 的错误处理：没 Key、业务错误码都要给出明确异常。"""

    async def test_未配置Key时抛异常(self, monkeypatch):
        client = qw.QWeatherClient(api_key="")
        monkeypatch.setattr(client, "api_key", "")
        with pytest.raises(RuntimeError, match="QWEATHER_API_KEY"):
            await client._get("/weather/now", "101280101")

    async def test_业务错误码抛异常(self, respx_mock):
        client = qw.QWeatherClient(api_key="fake", base_url="https://qw.test")
        respx_mock.get("https://qw.test/weather/now").mock(
            return_value=httpx.Response(200, json={"code": "401", "msg": "invalid key"})
        )
        with pytest.raises(RuntimeError, match="和风天气 API 错误"):
            await client._get("/weather/now", "101280101")

    async def test_正常返回数据(self, respx_mock):
        client = qw.QWeatherClient(api_key="fake", base_url="https://qw.test")
        respx_mock.get("https://qw.test/weather/now").mock(
            return_value=httpx.Response(200, json=NOW_SAMPLE)
        )
        data = await client._get("/weather/now", "101280101")
        assert data["code"] == "200"


class TestFetch:
    """fetch 聚合：实时 + 预报 + 预警。"""

    async def test_聚合三类数据(self, monkeypatch):
        client = qw.QWeatherClient(api_key="fake")

        async def fake_get(path, location):
            if path == "/weather/now":
                return NOW_SAMPLE
            if path == "/weather/7d":
                return DAILY_SAMPLE
            return {"code": "200", "warning": []}

        monkeypatch.setattr(client, "_get", fake_get)
        bundle = await client.fetch("101280101")

        assert bundle.current.temperature == 30.0
        assert len(bundle.daily) == 2
        assert bundle.alerts == []
        assert bundle.location_code == "101280101"

    async def test_预警解析为中文(self, monkeypatch):
        client = qw.QWeatherClient(api_key="fake")

        async def fake_get(path, location):
            if path == "/weather/now":
                return NOW_SAMPLE
            if path == "/weather/7d":
                return DAILY_SAMPLE
            return {
                "code": "200",
                "warning": [
                    {
                        "level": "Yellow",
                        "type": "Thunder",
                        "title": "雷电黄色预警",
                        "text": "未来 6 小时有雷电活动",
                    }
                ],
            }

        monkeypatch.setattr(client, "_get", fake_get)
        bundle = await client.fetch("101280101")

        assert len(bundle.alerts) == 1
        assert bundle.alerts[0].level == "黄色"
        assert bundle.alerts[0].type == "雷电"

    async def test_预警接口报错不影响主流程(self, monkeypatch):
        """预警是"锦上添花"，挂了也不能让整个天气查询失败。"""
        client = qw.QWeatherClient(api_key="fake")

        async def fake_get(path, location):
            if path == "/weather/now":
                return NOW_SAMPLE
            if path == "/weather/7d":
                return DAILY_SAMPLE
            raise RuntimeError("预警接口 403（和风已废弃该接口）")

        monkeypatch.setattr(client, "_get", fake_get)
        bundle = await client.fetch("101280101")

        assert bundle.current.temperature == 30.0  # 主数据正常
        assert bundle.alerts == []  # 预警降级为空


class TestMappings:
    def test_常见天气图标都有中文描述(self):
        for code in (100, 104, 302, 305, 400, 500, 502):
            assert qw.QW_ICON_DESC[code]

    def test_预警等级与类型有中文映射(self):
        assert qw.QW_ALERT_LEVEL["Yellow"] == "黄色"
        assert qw.QW_ALERT_TYPE["Thunder"] == "雷电"

    def test_风力等级表覆盖0到12级(self):
        assert set(qw.WIND_LEVEL) == set(range(13))
