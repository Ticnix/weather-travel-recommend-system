"""统一 API 响应体封装。"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一响应结构：{ code, message, data }。"""

    code: int = 0
    message: str = "success"
    data: T | None = None

    @classmethod
    def ok(cls, data: Any = None, message: str = "success") -> "ApiResponse":
        return cls(code=0, message=message, data=data)

    @classmethod
    def fail(cls, code: int = 1, message: str = "error", data: Any = None) -> "ApiResponse":
        return cls(code=code, message=message, data=data)


def success(data: Any = None, message: str = "success") -> dict:
    """返回标准成功响应（dict，便于直接 FastAPI 返回）。"""
    return ApiResponse.ok(data=data, message=message).model_dump()


def error(code: int = 1, message: str = "error", data: Any = None) -> dict:
    return ApiResponse.fail(code=code, message=message, data=data).model_dump()
