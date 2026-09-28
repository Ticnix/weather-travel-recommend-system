"""高德地图路线规划客户端。

能力：
- 地理编码（地址 → 经纬度）
- 路线规划（驾车/公交/步行，返回多套方案：耗时/距离/费用/换乘等）

设计：
- 配置了 AMAP_API_KEY 时走真实高德 API；
- 未配置 Key 或调用失败时，降级为「兜底路线」（基于城市坐标的直线距离估算），
  保证链路可端到端联调，Key 到位后无缝切换真实数据。
"""

from __future__ import annotations

import logging
import math
from typing import Any

import httpx

from app.core.config import settings
from app.services.city_dict import lookup_city

logger = logging.getLogger(__name__)

# 广州常见地标/站点坐标（兜底用，无高德 Key 时解析具体地点）
# 格式：名称 -> (经度, 纬度)
_GZ_LANDMARKS: dict[str, tuple[float, float]] = {
    "广州南站": (113.2693, 22.9916),
    "广州塔": (113.3245, 23.1065),
    "小蛮腰": (113.3245, 23.1065),
    "白云山": (113.2987, 23.1860),
    "珠江夜游": (113.2580, 23.1120),
    "珠江": (113.2580, 23.1120),
    "北京路": (113.2673, 23.1255),
    "天河城": (113.3270, 23.1320),
    "陈家祠": (113.2400, 23.1290),
    "越秀公园": (113.2640, 23.1420),
    "沙面": (113.2390, 23.1070),
    "广州东站": (113.3240, 23.1510),
    "白云机场": (113.3030, 23.3920),
    "长隆野生动物园": (113.3480, 23.0030),
    "广州火车站": (113.2560, 23.1510),
    "体育西路": (113.3220, 23.1320),
}


def _lookup_landmark(address: str) -> dict[str, Any] | None:
    """在本地地标表里查坐标（精确匹配 + 包含匹配）。"""
    a = address.strip()
    # 精确匹配
    if a in _GZ_LANDMARKS:
        lng, lat = _GZ_LANDMARKS[a]
        return {"lng": lng, "lat": lat, "formatted": a}
    # 包含匹配（"广州塔西门" -> 命中"广州塔"）
    for name, (lng, lat) in _GZ_LANDMARKS.items():
        if name in a or a in name:
            return {"lng": lng, "lat": lat, "formatted": name}
    return None


async def geocode(address: str, city: str | None = None) -> dict[str, Any] | None:
    """地理编码：地址 → {lng, lat, formatted}。失败返回 None。"""
    if not settings.AMAP_API_KEY:
        # 无 Key：优先查本地地标表，其次城市字典兜底
        landmark = _lookup_landmark(address)
        if landmark:
            return landmark
        city_info = lookup_city(address) or (lookup_city(city) if city else None)
        if city_info:
            return {"lng": city_info.lon, "lat": city_info.lat, "formatted": city_info.name}
        return None

    params = {
        "key": settings.AMAP_API_KEY,
        "address": address,
        "city": city or settings.AMAP_DEFAULT_CITY,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{settings.AMAP_BASE_URL}/geocode/geo", params=params)
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") == "1" and data.get("geocodes"):
            g = data["geocodes"][0]
            loc = g.get("location", "").split(",")
            if len(loc) == 2:
                return {
                    "lng": float(loc[0]),
                    "lat": float(loc[1]),
                    "formatted": g.get("formatted_address", address),
                }
    except Exception as exc:  # noqa: BLE001
        logger.warning("高德地理编码失败: %s", exc)
    return None


def list_landmarks() -> list[dict[str, Any]]:
    """返回内置常用地标（无高德 Key 时的兜底，也供前端「常用地点」快捷选择）。"""
    seen: set[tuple[float, float]] = set()
    items: list[dict[str, Any]] = []
    for name, (lng, lat) in _GZ_LANDMARKS.items():
        if (lng, lat) in seen:  # 「广州塔 / 小蛮腰」等别名共用坐标，只保留第一个
            continue
        seen.add((lng, lat))
        items.append({"name": name, "lng": lng, "lat": lat})
    return items


async def regeo(lat: float, lon: float) -> dict[str, Any] | None:
    """逆地理编码：坐标 → 所在行政区 {province, city, district, adcode, formatted}。

    为什么需要它：用户授权定位后拿到的是经纬度，而"南沙区"这种地名才是
    用户看得懂、也才能拿去查当地天气的键。无 Key 或失败返回 None（调用方回落城市中心）。
    """
    if not settings.AMAP_API_KEY:
        return None

    params = {
        "key": settings.AMAP_API_KEY,
        # 高德是「经度,纬度」，和本函数参数顺序相反，别弄反
        "location": f"{lon},{lat}",
        "extensions": "base",
        "radius": "1000",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{settings.AMAP_BASE_URL}/geocode/regeo", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("高德逆地理编码失败: %s", exc)
        return None

    if data.get("status") != "1" or not data.get("regeocode"):
        return None

    comp = data["regeocode"].get("addressComponent") or {}

    def _first(value: Any) -> str:
        """高德的 city/district 在直辖市里是空数组，统一成字符串。"""
        if isinstance(value, list):
            return value[0] if value else ""
        return value or ""

    return {
        "province": _first(comp.get("province")),
        "city": _first(comp.get("city")) or _first(comp.get("province")),
        "district": _first(comp.get("district")),
        "adcode": _first(comp.get("adcode")),
        "formatted": data["regeocode"].get("formatted_address") or "",
    }


async def suggest_places(
    keyword: str,
    city: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """地点输入提示：关键词 → 候选地点列表（含精确经纬度）。

    供前端「输入联想」使用，选中后可直接把坐标传给路线规划，
    彻底避免「地名解析不出来 → 报错」的问题。

    未配置 Key 时降级为在本地地标表里模糊匹配。
    """
    kw = (keyword or "").strip()
    if not kw:
        return []

    if not settings.AMAP_API_KEY:
        hits = [it for it in list_landmarks() if kw in it["name"] or it["name"] in kw]
        return hits[:limit]

    params = {
        "key": settings.AMAP_API_KEY,
        "keywords": kw,
        "city": city or settings.AMAP_DEFAULT_CITY,
        "citylimit": "false",  # 允许跨城搜索
        "datatype": "all",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{settings.AMAP_BASE_URL}/assistant/inputtips", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("高德输入提示失败: %s", exc)
        return []

    if data.get("status") != "1":
        return []

    items: list[dict[str, Any]] = []
    for tip in data.get("tips") or []:
        name = (tip.get("name") or "").strip()
        loc = tip.get("location") or ""
        # 行政区、公交线路等条目没有坐标，无法用于路线规划，直接跳过
        if not name or "," not in loc:
            continue
        try:
            lng_str, lat_str = loc.split(",")[:2]
            lng, lat = float(lng_str), float(lat_str)
        except ValueError:
            continue
        items.append(
            {
                "name": name,
                "district": tip.get("district") or "",
                "address": tip.get("address") or "",
                "lng": lng,
                "lat": lat,
            }
        )
        if len(items) >= limit:
            break
    return items


# 高德 POI 类型码（place/text 的 types 参数）
POI_SCENERY = "110000"  # 风景名胜
POI_FOOD = "050000"  # 餐饮服务
POI_SHOPPING = "060000"  # 购物服务


async def search_pois(
    keyword: str,
    city: str | None = None,
    types: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """POI 检索：关键词（可选类型）→ 候选地点，**每条都带所属行政区**。

    与 suggest_places（输入联想）的分工：
    inputtips 是"打字联想"，返回的是常见叫法、没有类型也没有行政区；
    place/text 是真正的 POI 检索，能按类型过滤，并且返回 adname（所在区）——
    「把行程限定在某个区」只能靠它：高德的 `city` 参数**不认区名**，
    传 city=南沙区 会被直接忽略（实测返回的是北京的结果）。

    无 Key 或调用失败时返回空列表，由调用方决定怎么兜底。
    """
    kw = (keyword or "").strip()
    if not kw:
        return []

    if not settings.AMAP_API_KEY:
        # 无 Key：本地地标兜底（没有行政区信息，区域过滤会自然失效）
        return [
            {
                "name": item["name"],
                "district": "",
                "address": "",
                "lng": item["lng"],
                "lat": item["lat"],
            }
            for item in list_landmarks()
            if kw in item["name"]
        ][:limit]

    params = {
        "key": settings.AMAP_API_KEY,
        "keywords": kw,
        "city": city or settings.AMAP_DEFAULT_CITY,
        "offset": str(min(max(limit, 1), 25)),
        "page": "1",
        "extensions": "base",
    }
    if types:
        params["types"] = types
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(f"{settings.AMAP_BASE_URL}/place/text", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("高德 POI 检索失败: %s", exc)
        return []

    if data.get("status") != "1":
        return []

    items: list[dict[str, Any]] = []
    for poi in data.get("pois") or []:
        name = (poi.get("name") or "").strip()
        loc = poi.get("location") or ""
        if not name or "," not in loc:
            continue
        try:
            lng_str, lat_str = loc.split(",")[:2]
            lng, lat = float(lng_str), float(lat_str)
        except ValueError:
            continue
        address = poi.get("address")
        items.append(
            {
                "name": name,
                "district": poi.get("adname") or "",
                # 部分 POI 的 address 是数组，统一成字符串，避免调用方拿到列表
                "address": address if isinstance(address, str) else "",
                # POI 分类（如"风景名胜;公园广场;公园"）：调用方据此过滤住宅区/公司等非景点
                "type": poi.get("type") or "",
                "lng": lng,
                "lat": lat,
            }
        )
        if len(items) >= limit:
            break
    return items


async def plan_route(
    origin: str,
    destination: str,
    city: str | None = None,
    origin_point: dict[str, Any] | None = None,
    destination_point: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """路线规划：返回多套方案（真实高德：驾车 + 公交；兜底：多交通方式估算）。

    origin_point / destination_point：前端「输入联想」选中的地点坐标
    （形如 {"lng": 113.32, "lat": 23.10, "formatted": "广州塔"}）。
    传了就直接使用坐标、**跳过地理编码**，避免地名解析失败导致报错。

    返回结构：
    {
        "origin": "广州南站",
        "destination": "广州塔",
        "mode": "driving" | "fallback",
        "routes": [
            {"mode": "驾车", "duration_min": 35, "distance_km": 22.0, "cost": 15, "detail": "..."},
            ...
        ]
    }
    """
    # 优先走真实高德 API（驾车 + 公交，按耗时合并排序）
    if settings.AMAP_API_KEY:
        driving = await _plan_driving_amap(
            origin, destination, city, origin_point, destination_point
        )
        transit = await _plan_transit_amap(
            origin, destination, city, origin_point, destination_point
        )
        routes = []
        if driving and driving.get("routes"):
            routes.extend(driving["routes"])
        if transit and transit.get("routes"):
            routes.extend(transit["routes"])
        if routes:
            routes.sort(key=lambda r: r["duration_min"])
            return {
                "origin": origin,
                "destination": destination,
                "mode": "driving",
                "routes": routes,
            }

    # 兜底：基于坐标的直线距离估算（多交通方式）
    return await _plan_fallback(origin, destination, city, origin_point, destination_point)


async def _plan_transit_amap(
    origin: str,
    destination: str,
    city: str | None,
    o_point: dict[str, Any] | None = None,
    d_point: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """高德公交路线规划 API（含地铁）。"""
    # 前端已选点则直接用坐标，跳过地理编码
    o = o_point or await geocode(origin, city)
    d = d_point or await geocode(destination, city)
    if not o or not d:
        return None

    params = {
        "key": settings.AMAP_API_KEY,
        "origin": f"{o['lng']},{o['lat']}",
        "destination": f"{d['lng']},{d['lat']}",
        "city": city or settings.AMAP_DEFAULT_CITY,
        "extensions": "base",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.AMAP_BASE_URL}/direction/transit/integrated", params=params
            )
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") != "1" or not data.get("route", {}).get("transits"):
            return None

        routes = []
        for t in data["route"]["transits"][:3]:
            distance_km = round(float(t.get("distance", 0)) / 1000, 1)
            duration_min = round(float(t.get("duration", 0)) / 60)
            cost = float(t.get("cost", 0))
            # 公交费用通常很低，取实际
            cost = round(cost, 1) if cost else round(max(2, distance_km * 0.3), 1)
            # 提取换乘信息
            segments = t.get("segments", [])
            transit_lines = []
            for seg in segments:
                bus = seg.get("bus", {})
                if bus and bus.get("buslines"):
                    for line in bus["buslines"][:1]:
                        transit_lines.append(f"{line.get('type', '公交')}{line.get('name', '')}")
            detail = " → ".join(transit_lines[:3]) or "地铁/公交可达"
            routes.append(
                {
                    "mode": "地铁/公交",
                    "duration_min": duration_min,
                    "distance_km": distance_km,
                    "cost": cost,
                    "detail": detail,
                }
            )
        return {
            "origin": origin,
            "destination": destination,
            "mode": "transit",
            "routes": routes,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("高德公交路线规划失败: %s", exc)
        return None


async def _plan_driving_amap(
    origin: str,
    destination: str,
    city: str | None,
    o_point: dict[str, Any] | None = None,
    d_point: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """高德驾车路线规划 API。"""
    # 前端已选点则直接用坐标，跳过地理编码
    o = o_point or await geocode(origin, city)
    d = d_point or await geocode(destination, city)
    if not o or not d:
        return None

    params = {
        "key": settings.AMAP_API_KEY,
        "origin": f"{o['lng']},{o['lat']}",
        "destination": f"{d['lng']},{d['lat']}",
        "extensions": "base",
        "strategy": "10",  # 速度优先 + 不走高速等备选策略
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{settings.AMAP_BASE_URL}/direction/driving", params=params)
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") != "1":
            return None

        routes = []
        for path in data["route"]["paths"][:3]:
            # 高德距离单位是米，耗时秒
            distance_km = round(float(path.get("distance", 0)) / 1000, 1)
            duration_min = round(float(path.get("duration", 0)) / 60)
            # 费用估算：按 0.5 元/公里 + 过路费（简化）
            toll = float(path.get("tolls", 0))
            cost = round(distance_km * 0.5 + toll, 1)
            steps = path.get("steps", [])
            detail = " → ".join(s.get("instruction", "") for s in steps[:3])
            routes.append(
                {
                    "mode": "驾车",
                    "duration_min": duration_min,
                    "distance_km": distance_km,
                    "cost": cost,
                    "detail": detail or "按导航行驶",
                }
            )
        return {
            "origin": origin,
            "destination": destination,
            "mode": "driving",
            "routes": routes,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("高德路线规划失败: %s", exc)
        return None


def _haversine_km(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """两点球面距离（Haversine 公式），单位 km。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


async def _plan_fallback(
    origin: str,
    destination: str,
    city: str | None,
    o_point: dict[str, Any] | None = None,
    d_point: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """兜底路线规划：用城市坐标算直线距离，衍生多种交通方式的估算方案。"""
    o = o_point or await geocode(origin, city)
    d = d_point or await geocode(destination, city)
    if not o or not d:
        return {
            "origin": origin,
            "destination": destination,
            "mode": "fallback",
            "routes": [],
            "error": "无法解析起终点坐标，请提供更具体的地点名或城市名",
        }

    dist = _haversine_km(o["lng"], o["lat"], d["lng"], d["lat"])
    # 直线距离 → 各交通方式估算（经验系数），并按合理距离区间过滤
    candidate_routes = [
        {
            "mode": "步行",
            "duration_min": round(dist / 5 * 60),  # 步行 5km/h
            "distance_km": round(dist, 1),
            "cost": 0,
            "detail": "适合短距离",
            "max_km": 3,  # 步行合理上限 3km
        },
        {
            "mode": "骑行",
            "duration_min": round(dist / 15 * 60),  # 骑行 15km/h
            "distance_km": round(dist, 1),
            "cost": round(max(1.5, dist * 1.5), 1),  # 共享单车约 1.5 元起步
            "detail": "适合中短距离",
            "max_km": 15,  # 骑行合理上限 15km
        },
        {
            "mode": "驾车",
            "duration_min": round(dist / 30 * 60),  # 市区驾车均速 30km/h
            "distance_km": round(dist * 1.3, 1),  # 实际路网系数 1.3
            "cost": round(dist * 1.3 * 0.5, 1),  # 0.5 元/公里
            "detail": "适合长距离或携带行李",
            "max_km": 1000,  # 驾车几乎不限
        },
        {
            "mode": "地铁/公交",
            "duration_min": round(dist / 20 * 60 + 15),  # 公交均速 20km/h + 等车 15min
            "distance_km": round(dist * 1.4, 1),
            "cost": round(max(2, dist * 0.5), 1),  # 起步 2 元
            "detail": "经济实惠，需步行到站点",
            "max_km": 1000,  # 公交不限
        },
    ]
    # 过滤超距离方案 + 去掉 max_km 内部字段
    routes = [
        {k: v for k, v in r.items() if k != "max_km"}
        for r in candidate_routes
        if dist <= r["max_km"]
    ]
    # 按耗时排序
    routes.sort(key=lambda r: r["duration_min"])
    return {
        "origin": origin,
        "destination": destination,
        "mode": "fallback",
        "routes": routes,
    }
