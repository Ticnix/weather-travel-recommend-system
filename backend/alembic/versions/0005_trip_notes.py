"""add trip_notes

新增「行程笔记」表：用户自由撰写的 Markdown 文档（攻略 / 清单 / 备忘）。
与 itineraries（结构化行程，用于天气提醒）互补，支持编辑、文件导入与导出。

Revision ID: 0005_trip_notes
Revises: 0004_news_full_text
Create Date: 2026-09-14

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_trip_notes"
down_revision: Union[str, None] = "0004_news_full_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS trip_notes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            note_date VARCHAR(10),
            location VARCHAR(128),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_trip_notes_user_id ON trip_notes (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS trip_notes")
