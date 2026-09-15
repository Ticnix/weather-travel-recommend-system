"""notification prefs

新增通知偏好表：每日早报开关 + 推送小时（免打扰粒度为小时，
由每小时分发的 Celery 任务按用户各自的 hour 过滤）。

Revision ID: 0007_notification_prefs
Revises: 0006_notification
Create Date: 2026-09-15

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007_notification_prefs"
down_revision: Union[str, None] = "0006_notification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_prefs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            morning_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            morning_hour INTEGER NOT NULL DEFAULT 7,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notification_prefs")
