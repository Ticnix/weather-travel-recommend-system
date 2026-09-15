"""FastAPI 依赖：解析当前登录用户。"""

from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login", auto_error=True)
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/users/login", auto_error=False)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """从 Bearer Token 解析用户，用户不存在则 401。"""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效或过期的身份凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exc
    except jwt.PyJWTError:
        # from None：切断异常链，对外只暴露「凭证无效」，
        # 不把 JWT 解析的内部报错细节泄漏给客户端
        raise credentials_exc from None

    user = await db.scalar(select(User).where(User.id == int(sub)))
    if user is None or not user.is_active:
        raise credentials_exc
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_optional_user(
    token: Annotated[str | None, Depends(oauth2_scheme_optional)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """可选鉴权：匿名返回 None。用于允许匿名提交反馈等场景。"""
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        sub = payload.get("sub")
        if sub is None:
            return None
        return await db.scalar(select(User).where(User.id == int(sub)))
    except jwt.PyJWTError:
        return None


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
