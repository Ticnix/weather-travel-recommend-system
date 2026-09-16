"""用户相关 Pydantic Schema。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    nickname: str | None = None
    email: str | None = None
    role: str = "user"


class UserCreate(UserBase):
    password: str = Field(..., min_length=6, max_length=128)


class UserUpdate(BaseModel):
    nickname: str | None = None
    email: str | None = None
    avatar: str | None = None
    role: str | None = None
    is_active: bool | None = None
    # 体质偏好（Day 37）：normal / cold / heat，用于生活指数个性化排序
    body_preference: Literal["normal", "cold", "heat"] | None = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    avatar: str | None = None
    is_active: bool = True
    body_preference: str = "normal"
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
