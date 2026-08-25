"""用户私有知识库 Schema。"""

from pydantic import BaseModel, Field


class UserKnowledgeCreate(BaseModel):
    """上传文档请求。"""

    title: str = Field(..., min_length=1, max_length=255, description="文档/计划标题")
    content: str = Field(..., min_length=1, description="文档正文内容")
    source: str = Field(default="upload", max_length=64, description="来源类型，如 itinerary/note")


class UserKnowledgeSearch(BaseModel):
    """私有知识库检索请求。"""

    query: str = Field(..., min_length=1, description="检索问题")
    top_k: int = Field(default=5, ge=1, le=10, description="返回条数")