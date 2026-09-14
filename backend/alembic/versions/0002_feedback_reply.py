"""add feedback reply columns

补记：Day20 的反馈回复功能（reply / reply_at 两列）当时是在原开发机上**手工 ALTER**
完成的，未生成迁移文件。导致在新环境按 `alembic upgrade head` 建库后这两列缺失，
管理端「用户反馈管理」查询报 `UndefinedColumnError: column feedback.reply does not exist`。
本迁移将这两列正式纳入版本管理，并保证幂等（旧环境已手工加过也不会报错）。

Revision ID: 0002_feedback_reply
Revises: 0001_initial
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_feedback_reply"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS：兼容已经手工 ALTER 过的旧环境
    op.execute("ALTER TABLE feedback ADD COLUMN IF NOT EXISTS reply TEXT")
    op.execute(
        "ALTER TABLE feedback ADD COLUMN IF NOT EXISTS reply_at TIMESTAMP WITH TIME ZONE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE feedback DROP COLUMN IF EXISTS reply_at")
    op.execute("ALTER TABLE feedback DROP COLUMN IF EXISTS reply")
