"""add news source_url

为资讯增加原文链接字段，用于详情页内嵌展示原文（采集自中央气象台的预警）。

Revision ID: 0003_news_source_url
Revises: 0002_feedback_reply
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003_news_source_url"
down_revision: Union[str, None] = "0002_feedback_reply"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS source_url VARCHAR(512)")


def downgrade() -> None:
    op.execute("ALTER TABLE news DROP COLUMN IF EXISTS source_url")
