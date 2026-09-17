"""notification categories

通知偏好新增类型开关（预警、行程提醒），发送记录新增类型列——
让「推送历史」能说明每条是什么类型，也能查到"被哪条偏好拦下了"。

Revision ID: 0010_notification_categories
Revises: 0009_life_indices
Create Date: 2026-09-16

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010_notification_categories"
down_revision: Union[str, None] = "0009_life_indices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE notification_prefs ADD COLUMN IF NOT EXISTS "
        "alert_enabled BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE notification_prefs ADD COLUMN IF NOT EXISTS "
        "itinerary_enabled BOOLEAN NOT NULL DEFAULT true"
    )
    # 历史行按 system 处理：它们确实不属于任何一个可关闭的类型
    op.execute(
        "ALTER TABLE notification_logs ADD COLUMN IF NOT EXISTS "
        "category VARCHAR(16) NOT NULL DEFAULT 'system'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE notification_logs DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE notification_prefs DROP COLUMN IF EXISTS itinerary_enabled")
    op.execute("ALTER TABLE notification_prefs DROP COLUMN IF EXISTS alert_enabled")
