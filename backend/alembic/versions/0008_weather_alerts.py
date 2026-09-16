"""weather alerts

新增天气预警记录表：fingerprint 去重键用于识别「新发布的预警」，
从而支撑「一发布就推送、同一条不重复推」。

Revision ID: 0008_weather_alerts
Revises: 0007_notification_prefs
Create Date: 2026-09-16

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008_weather_alerts"
down_revision: Union[str, None] = "0007_notification_prefs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS weather_alerts (
            id SERIAL PRIMARY KEY,
            fingerprint VARCHAR(32) NOT NULL UNIQUE,
            city VARCHAR(64) NOT NULL,
            level VARCHAR(16) NOT NULL,
            type VARCHAR(32) NOT NULL DEFAULT '',
            title VARCHAR(255) NOT NULL,
            detail TEXT,
            first_seen_at TIMESTAMPTZ NOT NULL,
            last_seen_at TIMESTAMPTZ NOT NULL,
            notified_at TIMESTAMPTZ,
            notified_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_weather_alerts_city ON weather_alerts (city)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_weather_alerts_last_seen_at "
        "ON weather_alerts (last_seen_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS weather_alerts")
