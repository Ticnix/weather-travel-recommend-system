"""用户相关 Pydantic Schema。"""

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 邮箱格式：不追求 RFC 完备（那需要 email-validator 依赖），
# 只挡掉明显非法的输入（缺 @、缺域名点号、含空格），避免脏数据进库。
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_email(value: str | None) -> str | None:
    """空串按「未填写」处理（前端解绑会传空串），并校验格式。"""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if not _EMAIL_RE.match(value):
        raise ValueError("邮箱格式不正确")
    return value


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    nickname: str | None = None
    email: str | None = None
    role: str = "user"

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        return _normalize_email(value)


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

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        return _normalize_email(value)


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
