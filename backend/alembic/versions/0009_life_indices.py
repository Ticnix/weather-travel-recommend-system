"""life indices

新增生活指数时序表（支持按天对比），并给用户表加体质偏好字段
（用于生活指数的个性化排序）。

Revision ID: 0009_life_indices
Revises: 0008_weather_alerts
Create Date: 2026-09-16

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009_life_indices"
down_revision: Union[str, None] = "0008_weather_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS life_indices (
            id SERIAL PRIMARY KEY,
            city VARCHAR(64) NOT NULL,
            date VARCHAR(10) NOT NULL,
            type_code VARCHAR(4) NOT NULL,
            name VARCHAR(64) NOT NULL,
            level VARCHAR(8) NOT NULL DEFAULT '',
            category VARCHAR(32) NOT NULL DEFAULT '',
            text TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_life_indices_city_date_type UNIQUE (city, date, type_code)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_life_indices_city ON life_indices (city)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_life_indices_date ON life_indices (date)")
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "body_preference VARCHAR(16) NOT NULL DEFAULT 'normal'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS body_preference")
    op.execute("DROP TABLE IF EXISTS life_indices")
