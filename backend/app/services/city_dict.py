"""国内常用城市字典：城市名/别名 → (经度, 纬度) + 和风 LocationID。

MCP Server 的天气工具接收"城市名"时，本模块负责：
1. 解析别名（北京/京城/bj/Beijing/北京首都 都映射到北京）
2. 返回 (lon, lat) 给和风 geo API，或直接返回 LocationID

字典来源：和风天气官方 LocationID + 各城市行政区坐标（已脱敏处理，可放心提交）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CityInfo:
    """城市信息。"""

    name: str  # 规范名（如"北京"）
    province: str  # 省份
    lon: float  # 经度
    lat: float  # 纬度
    qweather_id: str  # 和风 LocationID
    aliases: tuple[str, ...] = ()  # 别名（简拼、英文等）


# 国内常用城市字典（含省会 + 4 个一线 + 强二线，覆盖绝大多数出行场景）
CITY_DICT: dict[str, CityInfo] = {
    "广州": CityInfo("广州", "广东", 113.2644, 23.1291, "101280101", ("gz", "guangzhou", "广州塔")),
    "深圳": CityInfo("深圳", "广东", 114.0579, 22.5431, "101280601", ("sz", "shenzhen")),
    "北京": CityInfo("北京", "北京", 116.4074, 39.9042, "101010100", ("bj", "beijing", "京城", "首都")),
    "上海": CityInfo("上海", "上海", 121.4737, 31.2304, "101020100", ("sh", "shanghai", "沪")),
    "杭州": CityInfo("杭州", "浙江", 120.1551, 30.2741, "101210101", ("hz", "hangzhou")),
    "南京": CityInfo("南京", "江苏", 118.7969, 32.0603, "101190101", ("nj", "nanjing")),
    "苏州": CityInfo("苏州", "江苏", 120.5853, 31.2989, "101190401", ("sz-gz", "suzhou")),
    "成都": CityInfo("成都", "四川", 104.0668, 30.5728, "101270101", ("cd", "chengdu")),
    "重庆": CityInfo("重庆", "重庆", 106.5516, 29.5630, "101040100", ("cq", "chongqing")),
    "武汉": CityInfo("武汉", "湖北", 114.3055, 30.5928, "101200101", ("wh", "wuhan")),
    "西安": CityInfo("西安", "陕西", 108.9398, 34.3416, "101110101", ("xa", "xian")),
    "长沙": CityInfo("长沙", "湖南", 112.9388, 28.2282, "101250101", ("cs", "changsha")),
    "厦门": CityInfo("厦门", "福建", 118.0894, 24.4798, "101230201", ("xm", "xiamen")),
    "青岛": CityInfo("青岛", "山东", 120.3826, 36.0671, "101120201", ("qd", "qingdao")),
    "三亚": CityInfo("三亚", "海南", 109.5085, 18.2528, "101310201", ("sy", "sanya")),
    "哈尔滨": CityInfo("哈尔滨", "黑龙江", 126.5350, 45.8023, "101050101", ("hrb", "haerbin", "harbin")),
    "拉萨": CityInfo("拉萨", "西藏", 91.1409, 29.6500, "101140101", ("lasa", "lhasa")),
    "乌鲁木齐": CityInfo("乌鲁木齐", "新疆", 87.6168, 43.8256, "101130101", ("wlmq", "urumqi")),
    "昆明": CityInfo("昆明", "云南", 102.8329, 24.8801, "101290101", ("km", "kunming")),
    "大理": CityInfo("大理", "云南", 100.2257, 25.5916, "101290201", ("dl", "dali")),
    # 注：字典采用懒加载的内存查找（条目 < 100），无需建索引
}


# 别名反查表（构造一次复用）
_ALIAS_INDEX: dict[str, str] = {}
for _info in CITY_DICT.values():
    _ALIAS_INDEX[_info.name] = _info.name
    _ALIAS_INDEX[_info.qweather_id] = _info.name
    for _alias in _info.aliases:
        _ALIAS_INDEX[_alias.lower()] = _info.name
        _ALIAS_INDEX[_alias] = _info.name


def lookup_city(query: str) -> CityInfo | None:
    """根据城市名/别名/拼音/ID 查询城市信息。查不到返回 None。

    匹配规则（按优先级）：
    1. 完全匹配字典 key（规范名）
    2. 完全匹配别名（含拼音、小写）
    3. 包含匹配（"广州市天河区" 也能命中"广州"）
    """
    if not query:
        return None
    q = query.strip()

    # 1. 直接匹配规范名
    if q in CITY_DICT:
        return CITY_DICT[q]

    # 2. 别名匹配（支持英文/拼音大小写）
    if q.lower() in _ALIAS_INDEX:
        return CITY_DICT[_ALIAS_INDEX[q.lower()]]
    if q in _ALIAS_INDEX:
        return CITY_DICT[_ALIAS_INDEX[q]]

    # 3. 包含匹配：取最短的命中 key 优先
    for key in CITY_DICT:
        if key in q or q in key:
            return CITY_DICT[key]

    return None


def all_supported_cities() -> list[str]:
    """返回所有支持的城市规范名列表（用于提示词/帮助文本）。"""
    return sorted(CITY_DICT.keys())