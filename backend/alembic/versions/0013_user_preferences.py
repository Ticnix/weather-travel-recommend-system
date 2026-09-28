"""用户偏好表

Day 55：一次录入偏好（怕晒、带老人、偏爱户外…），对话/穿搭/排程全部遵循。

**为什么是独立新表而不是 users 表加列**：本项目线上用 `create_all`，
它只会创建缺失的**表**，不会给已存在的表补**列**
（Day 37 的 `users.body_preference`、Day 52 的 `risk_enabled` 都为此走过迁移）。
独立表 + JSONB 还有第二个好处：以后加偏好项**不用再写迁移**。

Revision ID: 0013_user_preferences
Revises: 0012_notification_risk
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013_user_preferences"
down_revision: Union[str, None] = "0012_notification_risk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            user_id INTEGER NOT NULL PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_preferences")
