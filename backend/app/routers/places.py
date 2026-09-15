"""地点服务接口：输入联想 + 常用地点。

供用户端「智能推荐」选择出发地/目的地：
- `/suggest`：关键词 → 候选地点（含精确坐标），前端做输入联想下拉
- `/landmarks`：内置常用地点，前端做「常用地点」快捷填入（零 Key 兜底）

选中地点后前端会把坐标一并传给规划接口，从而跳过地名解析，避免报错。
"""

from fastapi import APIRouter, Query

from app.core.response import success
from app.services import amap_client

router = APIRouter(prefix="/api/v1/places", tags=["地点服务"])


@router.get("/suggest", response_model=dict)
async def suggest_places(
    keyword: str = Query(..., min_length=1, description="关键词，如「猎德」"),
    city: str | None = Query(None, description="限定城市，默认广州"),
    limit: int = Query(8, ge=1, le=20, description="返回条数上限"),
) -> dict:
    """地点输入联想：返回候选地点（名称 / 区域 / 经纬度）。

    数据来自高德「输入提示」API；未配置 Key 时降级为内置地标模糊匹配。
    """
    items = await amap_client.suggest_places(keyword, city, limit)
    return success(data={"items": items, "total": len(items)})


@router.get("/landmarks", response_model=dict)
async def list_landmarks() -> dict:
    """常用地点列表（内置广州地标），供前端快捷填入。"""
    items = amap_client.list_landmarks()
    return success(data={"items": items, "total": len(items)})
