"""全局异常处理与业务异常定义。"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.response import error


class BusinessError(Exception):
    """业务异常：携带 code 与 message。"""

    def __init__(self, message: str = "业务处理失败", code: int = 1) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(BusinessError)
    async def _biz(_: Request, exc: BusinessError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=error(code=exc.code, message=exc.message)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error(code=422, message="请求参数校验失败", data=exc.errors()),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
        msg = "数据唯一性冲突或约束错误"
        detail = str(exc.orig)
        if "unique" in detail.lower():
            msg = "数据已存在（唯一约束冲突）"
        return JSONResponse(status_code=status.HTTP_200_OK, content=error(code=409, message=msg))

    @app.exception_handler(SQLAlchemyError)
    async def _db(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_200_OK, content=error(code=500, message=f"数据库错误: {exc}")
        )

    @app.exception_handler(Exception)
    async def _unknown(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=error(code=500, message=f"服务器内部错误: {exc}"),
        )
