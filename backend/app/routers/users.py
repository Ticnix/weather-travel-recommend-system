"""用户模块：注册、登录、当前用户、CRUD。"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.response import success
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, TokenOut, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/v1/users", tags=["用户"])


@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    """用户注册（自动查重）。"""
    exists = await db.scalar(select(User.id).where(User.username == payload.username))
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="用户名已存在")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname,
        email=payload.email,
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return success(UserOut.model_validate(user).model_dump(), message="注册成功")


@router.post("/login", response_model=dict)
async def login(payload: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> dict:
    """用户名 + 密码登录，返回 JWT。"""
    user = await db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    user.last_login_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(subject=user.id, extra={"role": user.role})
    return success(TokenOut(access_token=token, user=UserOut.model_validate(user)).model_dump())


@router.get("/me", response_model=dict)
async def me(current: CurrentUser) -> dict:
    """获取当前登录用户信息（需鉴权）。"""
    return success(UserOut.model_validate(current).model_dump())


@router.get("", response_model=dict)
async def list_users(
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = 1,
    page_size: int = 20,
    keyword: str | None = None,
) -> dict:
    """用户列表（分页 + 关键字搜索），需鉴权。"""
    stmt = select(User)
    if keyword:
        stmt = stmt.where(User.username.ilike(f"%{keyword}%"))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = await db.scalars(
        stmt.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return success(
        {
            "items": [UserOut.model_validate(u).model_dump() for u in rows],
            "total": total or 0,
            "page": page,
            "page_size": page_size,
        }
    )


@router.get("/{user_id}", response_model=dict)
async def get_user(
    user_id: int, current: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return success(UserOut.model_validate(user).model_dump())


@router.put("/{user_id}", response_model=dict)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    current: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return success(UserOut.model_validate(user).model_dump(), message="更新成功")


@router.delete("/{user_id}", response_model=dict)
async def delete_user(
    user_id: int, current: CurrentUser, db: Annotated[AsyncSession, Depends(get_db)]
) -> dict:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    await db.delete(user)
    await db.commit()
    return success(message="删除成功")
