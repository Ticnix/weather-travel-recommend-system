"""首页仪表盘服务单元测试（聚焦可独立验证的纯函数）。

`_build_tips` / `_itinerary_hint` / `_resolve_city` 是首页"今日提醒"的核心逻辑，
把它们做成纯函数的好处在这里体现：**不需要数据库、不需要天气 API 就能验证**。
"""

from app.services import home_service as hs


class TestResolveCity:
    """从行程地点文本解析城市（支持跨城市行程）。"""

    def test_从地点解析城市(self):
        assert hs._resolve_city("上海迪士尼") == "上海"

    def test_城市名可直接解析(self):
        # 注意：city_dict 认的是「城市」，景点名（如白云山）不在其中，
        # 景点城市由 amap_client 的地标表负责，这里只验证城市解析路径
        assert hs._resolve_city("广州") == "广州"

    def test_无法解析返回None(self):
        assert hs._resolve_city("不存在的火星基地") is None

    def test_空值返回None(self):
        assert hs._resolve_city(None) is None


class TestBuildTips:
    """今日提醒生成规则。"""

    def test_有降水给出带伞提醒(self):
        tips = hs._build_tips("中雨", 28, 30, 15.0, [])
        assert any("降水" in t["title"] for t in tips)
        assert any(t["icon"] == "☔" for t in tips)

    def test_降水达到25mm升级为danger(self):
        tips = hs._build_tips("暴雨", 28, 30, 30.0, [])
        rain_tips = [t for t in tips if "降水" in t["title"]]
        assert rain_tips and rain_tips[0]["level"] == "danger"

    def test_小雨为info级别(self):
        tips = hs._build_tips("小雨", 28, 30, 2.0, [])
        rain_tips = [t for t in tips if "降水" in t["title"]]
        assert rain_tips and rain_tips[0]["level"] == "info"

    def test_高温给出防晒提醒(self):
        tips = hs._build_tips("晴", 35, 37, 0, [])
        assert any("高温" in t["title"] for t in tips)

    def test_低温给出保暖提醒(self):
        tips = hs._build_tips("多云", 8, 6, 0, [])
        assert any("降温" in t["title"] for t in tips)

    def test_强对流判为danger(self):
        tips = hs._build_tips("雷阵雨", 30, 32, 5.0, [])
        assert any(t["level"] == "danger" for t in tips)

    def test_体感明显偏高提示闷热(self):
        tips = hs._build_tips("阴", 30, 35, 0, [])
        assert any("体感" in t["title"] for t in tips)

    def test_天气平稳时给默认提醒(self):
        """不能返回空列表——首页需要始终有内容可展示。"""
        tips = hs._build_tips("多云", 22, 23, 0, [])
        assert len(tips) == 1
        assert tips[0]["title"] == "天气平稳"

    def test_天气预警会追加为提醒(self):
        class _Alert:
            title = "雷雨大风黄色预警"
            detail = "预计未来 3 小时有雷雨大风"

        tips = hs._build_tips("阴", 30, 31, 0, [_Alert()])
        assert any("预警" in t["title"] for t in tips)
        assert any(t["level"] == "danger" for t in tips)

    def test_每条提醒字段完整(self):
        tips = hs._build_tips("中雨", 33, 36, 12.0, [])
        assert all({"icon", "level", "title", "text"} <= set(t) for t in tips)
        assert all(t["level"] in ("info", "warning", "danger") for t in tips)


class TestItineraryHint:
    """行程逐条天气提示。"""

    def test_大雨建议带雨具或改期(self):
        hint = hs._itinerary_hint("中雨", 15.0, 28)
        assert ("带雨具" in hint) or ("改期" in hint)

    def test_强对流提示谨慎(self):
        hint = hs._itinerary_hint("雷阵雨", 2.0, 30)
        assert "谨慎" in hint

    def test_高温提示防晒(self):
        hint = hs._itinerary_hint("晴", 0, 35)
        assert "防晒" in hint

    def test_普通天气只拼基础信息(self):
        hint = hs._itinerary_hint("多云", 0, 26)
        assert "多云" in hint
        assert "26" in hint

    def test_无数据返回暂无预报(self):
        assert hs._itinerary_hint(None, None, None) == "暂无该日预报"
