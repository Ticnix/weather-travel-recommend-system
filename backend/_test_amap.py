"""高德 API 连通性测试"""
import asyncio
import httpx

API_KEY = "0ac1d95e22c899ca564c6a05afb9b81c"


async def main():
    # 1. 地理编码
    r1 = await httpx.AsyncClient(timeout=10.0).get(
        "https://restapi.amap.com/v3/geocode/geo",
        params={"key": API_KEY, "address": "广州南站", "city": "广州"},
    )
    print(f"地理编码: {r1.status_code}")
    d1 = r1.json()
    if d1.get("geocodes"):
        g = d1["geocodes"][0]
        print(f"  结果: {g['formatted_address']} @ {g['location']}")
    else:
        print(f"  错误: {d1.get('info')}")

    # 2. 路线规划
    r2 = await httpx.AsyncClient(timeout=10.0).get(
        "https://restapi.amap.com/v3/direction/driving",
        params={
            "key": API_KEY,
            "origin": "113.2693,22.9916",
            "destination": "113.3245,23.1065",
            "extensions": "base",
        },
    )
    print(f"\n路线规划: {r2.status_code}")
    d2 = r2.json()
    if d2.get("route", {}).get("paths"):
        p = d2["route"]["paths"][0]
        print(f"  距离: {int(p['distance'])/1000:.1f}km, 耗时: {int(p['duration'])/60:.0f}分钟")
        print(f"  过路费: {p.get('tolls', 0)}元")
    else:
        print(f"  错误: {d2.get('info')}")


asyncio.run(main())