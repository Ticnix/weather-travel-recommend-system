"""评分逻辑与辅助函数单元测试。

集中覆盖几个"容易被忽略、但业务上很关键"的纯函数：
- 出行方案的三维评分（时间 / 费用 / 天气）
- 穿搭灵感的平台识别与季节推导
- 资讯本地化判定、笔记标题推断
"""

import pytest

from app.services import outfit_inspiration as oi
from app.services import weather_news_service as wns
from app.services.trip_note_service import derive_title, parse_import_file
from skills.travel_planning.scripts import route_planner as rp


class TestRouteScoring:
    """出行方案评分：三者都归一化到 0~1，越高越好。"""

    def test_时间越短分越高(self):
        assert rp.time_score(10, 60) > rp.time_score(50, 60)

    def test_时间为0得满分(self):
        assert rp.time_score(0, 60) == 1.0

    def test_时间等于上限得0分(self):
        assert rp.time_score(60, 60) == 0.0

    def test_超过上限不为负(self):
        assert rp.time_score(120, 60) == 0.0

    def test_上限为0时避免除零(self):
        assert rp.time_score(10, 0) == 1.0

    def test_费用越低分越高(self):
        assert rp.cost_score(2, 20) > rp.cost_score(18, 20)

    def test_天气_降水扣分(self):
        dry = rp.weather_score("晴", 22, 28, 0)
        rainy = rp.weather_score("晴", 22, 28, 15)
        assert dry > rainy

    def test_天气_恶劣天气描述扣分(self):
        good = rp.weather_score("晴", 22, 28, 0)
        bad = rp.weather_score("雷阵雨", 22, 28, 0)
        assert good > bad

    def test_天气_极端温度扣分(self):
        mild = rp.weather_score("晴", 22, 28, 0)
        hot = rp.weather_score("晴", 32, 38, 0)
        assert mild > hot

    def test_天气分数始终在0到1之间(self):
        for desc in ("晴", "暴雨", "雷阵雨", "大雪", "雾霾"):
            s = rp.weather_score(desc, 5, 40, 28)
            assert 0.0 <= s <= 1.0

    def test_权重之和为1(self):
        total = rp.WEIGHT_TIME + rp.WEIGHT_COST + rp.WEIGHT_WEATHER
        assert total == pytest.approx(1.0)


class TestOutfitInspirationHelpers:
    """穿搭灵感的平台识别与季节推导。"""

    @pytest.mark.parametrize(
        ("url", "expect"),
        [
            ("https://www.douyin.com/video/123", "抖音"),
            ("https://www.xiaohongshu.com/explore/abc", "小红书"),
            ("https://weibo.com/xxx", "微博"),
            ("https://www.bilibili.com/video/BV1", "B站"),
            ("https://zhuanlan.zhihu.com/p/1", "知乎"),
            ("https://example.com/a", "网页"),
        ],
    )
    def test_按域名识别平台(self, url, expect):
        assert oi._platform_of(url) == expect

    @pytest.mark.parametrize(
        ("temp", "expect"),
        [
            (35.0, "夏季"),
            (27.0, "夏末初秋"),
            (20.0, "秋季"),
            (12.0, "深秋"),
            (3.0, "冬季"),
        ],
    )
    def test_按温度推导季节(self, temp, expect):
        assert oi._season_of(temp) == expect

    def test_平台的搜索直达链接齐全(self):
        portals = oi.build_portals("广州 秋季穿搭")
        platforms = {p["platform"] for p in portals}
        assert {"小红书", "抖音", "微博", "B站"} <= platforms

    def test_搜索链接对关键词做了URL编码(self):
        portals = oi.build_portals("广州 秋季穿搭")
        assert all(" " not in p["url"] for p in portals)


class TestNewsLocalization:
    """资讯本地化判定（Day 12 修复：只保留广州相关内容）。"""

    @pytest.mark.parametrize(
        "text",
        [
            "广州天气",
            "广东预警",
            "华南地区",
            "珠江夜游",
            "粤式早茶",
            "广州塔",
            "花城广场",
            "羊城晚报",
        ],
    )
    def test_本地关键词命中(self, text):
        assert wns._is_local(text) is True

    @pytest.mark.parametrize("text", ["北京天气", "上海迪士尼", "美国大峡谷", ""])
    def test_非本地内容不匹配(self, text):
        assert wns._is_local(text) is False

    def test_多字段任意命中即可(self):
        assert wns._is_local("今日降水", "广州多区预警") is True

    def test_全部为空返回False(self):
        assert wns._is_local(None, None) is False


class TestNoteTitleDerivation:
    """笔记标题自动推断（导入时的关键体验）。"""

    def test_优先取Markdown标题行(self):
        assert derive_title("# 广州攻略\n\n正文") == "广州攻略"

    def test_无标题行时取首个非空行(self):
        assert derive_title("\n\n长沙两日游\n- 岳麓山") == "长沙两日游"

    def test_空内容用兜底标题(self):
        assert derive_title("", "我的备用标题") == "我的备用标题"

    def test_纯空白也用兜底(self):
        assert derive_title("   \n  \n") == "未命名笔记"

    def test_超长标题被截断(self):
        assert len(derive_title("# " + "长" * 500)) == 255


class TestNoteImportParsing:
    """文件导入解析：.md/.txt 单篇、.json 批量。"""

    def test_解析md文件(self):
        items = parse_import_file("攻略.md", "# 长沙两日游\n- 岳麓山".encode())
        assert len(items) == 1
        assert items[0]["title"] == "长沙两日游"

    def test_解析txt文件(self):
        items = parse_import_file("贵州笔记.txt", "贵州五日游\n黄果树瀑布".encode())
        assert len(items) == 1
        assert items[0]["title"] == "贵州五日游"

    def test_txt内容全空白抛出ValueError(self):
        with pytest.raises(ValueError):
            parse_import_file("empty.txt", b"\n\n   ")

    def test_解析json单条(self):
        raw = '{"title": "上海行", "content": "外滩"}'.encode()
        items = parse_import_file("a.json", raw)
        assert len(items) == 1
        assert items[0]["title"] == "上海行"

    def test_解析json数组批量(self):
        raw = b'[{"title":"A","content":"1"},{"title":"B","content":"2"}]'
        items = parse_import_file("a.json", raw)
        assert len(items) == 2

    def test_json缺少标题时用正文推断(self):
        raw = '{"content": "# 自动标题\\n正文"}'.encode()
        items = parse_import_file("a.json", raw)
        assert items[0]["title"] == "自动标题"

    def test_json格式错误抛出ValueError(self):
        with pytest.raises(ValueError):
            parse_import_file("bad.json", b"{not json")

    def test_空文件抛出ValueError(self):
        with pytest.raises(ValueError):
            parse_import_file("empty.md", b"")

    def test_json无有效条目抛出ValueError(self):
        with pytest.raises(ValueError):
            parse_import_file("x.json", b"[]")
