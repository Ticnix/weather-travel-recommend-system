"""临时验证：没有视觉模型时，截图类图片能否靠离线 OCR 兜住（用完即删）。"""

import json

import httpx

BASE = "http://localhost:8000/api/v1"
login = httpx.post(
    f"{BASE}/users/login", json={"username": "admin", "password": "Admin@123456"}
).json()
H = {"Authorization": f"Bearer {login['data']['access_token']}"}

from app.services import ocr_service  # noqa: E402

print("OCR 引擎可用:", ocr_service.available())

raw = open("/tmp/shot.png", "rb").read()
resp = httpx.post(
    f"{BASE}/chat/attachments", files={"file": ("shot.png", raw, "image/png")}, headers=H, timeout=180
)
print("上传:", resp.status_code)
print(json.dumps(resp.json(), ensure_ascii=True)[:400])

aid = (resp.json().get("data") or {}).get("id")
if aid:
    tokens: list[str] = []
    with httpx.stream(
        "POST",
        f"{BASE}/chat/stream",
        json={
            "message": "这张截图里显示了什么？请用中文概括要点。",
            "conversation_id": "ocrdiag01",
            "attachments": [aid],
        },
        headers=H,
        timeout=180,
    ) as stream:
        for line in stream.iter_lines():
            if not line.startswith("data:"):
                continue
            try:
                evt = json.loads(line[5:].strip())
            except Exception:
                continue
            if evt.get("type") == "token":
                tokens.append(evt.get("content", ""))
    print("回答:", "".join(tokens)[:320])

# 纯色图（无文字）应当走"看不了图"的提示，而不是编造内容
import io  # noqa: E402

from PIL import Image  # noqa: E402

buf = io.BytesIO()
Image.new("RGB", (200, 120), (120, 170, 210)).save(buf, format="PNG")
resp2 = httpx.post(
    f"{BASE}/chat/attachments",
    files={"file": ("sky.png", buf.getvalue(), "image/png")},
    headers=H,
    timeout=120,
)
print("纯色图上传:", resp2.status_code, json.dumps(resp2.json(), ensure_ascii=True)[:220])
