"""密码哈希与 JWT 工具。

说明：使用标准库 hashlib(secrets) 实现 PBKDF2-HMAC-SHA256 密码哈希，
避免额外依赖（passlib/bcrypt）。生产环境可替换为 bcrypt。
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import settings

_PBKDF2_ALGORITHM = "sha256"
_PBKDF2_ROUNDS = 100_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """返回 `pbkdf2$<salt_hex>$<hash_hex>` 格式。"""
    salt = secrets.token_bytes(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(_PBKDF2_ALGORITHM, password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2${_PBKDF2_ALGORITHM}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验明文密码与存储哈希是否一致。"""
    try:
        scheme, algo, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "pbkdf2":
        return False
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac(algo, password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return hmac.compare_digest(dk.hex(), hash_hex)


def create_access_token(subject: str | int, extra: dict[str, Any] | None = None) -> str:
    """生成 JWT。payload 含 sub 与 exp。"""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """解码并校验 JWT，失败抛 jwt.PyJWTError。"""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
