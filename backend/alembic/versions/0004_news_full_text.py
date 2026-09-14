"""add news full_text

为资讯增加「原文正文」字段：采集类资讯（联网搜索 / 中国天气网）抓取原文正文后存入，
详情页可直接阅读完整内容，不再依赖 iframe 内嵌
（多数新闻站设置了 X-Frame-Options / CSP frame-ancestors，内嵌会被浏览器拒绝而空白）。

Revision ID: 0004_news_full_text
Revises: 0003_news_source_url
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004_news_full_text"
down_revision: Union[str, None] = "0003_news_source_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE news ADD COLUMN IF NOT EXISTS full_text TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE news DROP COLUMN IF EXISTS full_text")
