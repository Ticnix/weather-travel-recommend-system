import urllib.request
import json

# 阿里云 DataV GeoJSON 接口（免费公开）：广州行政区划边界
# adcode 440100 = 广州市
url = "https://geo.datav.aliyun.com/areas_v3/bound/440100_full.json"

req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read())
    features = data.get("features", [])
    print("区划数量:", len(features))
    for f in features:
        name = f.get("properties", {}).get("name")
        print("  -", name)
    with open("guangzhou_districts.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print("已保存 guangzhou_districts.json")
except Exception as e:
    print("拉取失败:", e)
