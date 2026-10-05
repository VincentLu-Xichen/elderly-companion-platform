"""add course lesson tracking

Revision ID: a74c1d3e9b20
Revises: f41c9e2a6d70
Create Date: 2026-07-30

This revision is retained so databases created by the earlier structured-course
prototype can upgrade to the conversational course schema without losing data.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a74c1d3e9b20"
down_revision: Union[str, None] = "f41c9e2a6d70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("lesson_id", sa.String(length=40), nullable=True))
    op.add_column("conversations", sa.Column("lesson_version", sa.String(length=40), nullable=True))
    op.create_index("ix_conversations_lesson_id", "conversations", ["lesson_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_conversations_lesson_id", table_name="conversations")
    op.drop_column("conversations", "lesson_version")
    op.drop_column("conversations", "lesson_id")
