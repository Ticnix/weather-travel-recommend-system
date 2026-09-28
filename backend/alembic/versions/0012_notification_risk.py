"""行程天气预警的通知开关

Day 51 的行程冲突扫描要提前 1~3 天提醒用户"预报与你的行程冲突了"，
这类通知必须能**单独关掉**——它比"出发前 30 分钟提醒"更主动，
有人就是不想被提前打扰。

新增的是列而不是表，所以必须走迁移：本项目线上用 `create_all`，
它只会创建缺失的**表**，不会给已存在的表补**列**
（Day 37 的 `users.body_preference` 就踩过这个坑）。

Revision ID: 0012_notification_risk
Revises: 0011_timescale_analytics
Create Date: 2026-09-23

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012_notification_risk"
down_revision: Union[str, None] = "0011_timescale_analytics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 默认 true：和其余类型开关一致——用户没表达过意愿时，默认值应该是有用的那一边
    op.execute(
        "ALTER TABLE notification_prefs ADD COLUMN IF NOT EXISTS "
        "risk_enabled BOOLEAN NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE notification_prefs DROP COLUMN IF EXISTS risk_enabled")
