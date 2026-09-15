"""notification tables

新增通知基础设施两张表：
- push_subscriptions：浏览器推送订阅（Web Push，每台设备一条，endpoint 全局唯一）
- notification_logs：通知发送记录（所有通道，含成功/失败/跳过，可查询审计）

Revision ID: 0006_notification
Revises: 0005_trip_notes
Create Date: 2026-09-15

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006_notification"
down_revision: Union[str, None] = "0005_trip_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            endpoint TEXT NOT NULL UNIQUE,
            p256dh VARCHAR(255) NOT NULL,
            auth VARCHAR(255) NOT NULL,
            user_agent VARCHAR(255),
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_push_subscriptions_user_id "
        "ON push_subscriptions (user_id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel VARCHAR(16) NOT NULL,
            title VARCHAR(200) NOT NULL,
            body TEXT,
            url VARCHAR(500),
            status VARCHAR(16) NOT NULL,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notification_logs_user_id "
        "ON notification_logs (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_notification_logs_created_at "
        "ON notification_logs (created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notification_logs")
    op.execute("DROP TABLE IF EXISTS push_subscriptions")
