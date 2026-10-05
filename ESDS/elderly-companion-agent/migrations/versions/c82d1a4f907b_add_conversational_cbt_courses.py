"""add conversational CBT courses

Revision ID: c82d1a4f907b
Revises: a74c1d3e9b20
Create Date: 2026-07-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c82d1a4f907b"
down_revision: Union[str, None] = "a74c1d3e9b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    conversation_columns = {column["name"] for column in inspector.get_columns("conversations")}
    if "active_course_key" not in conversation_columns:
        op.add_column("conversations", sa.Column("active_course_key", sa.String(length=100), nullable=True))
    conversation_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("conversations")}
    if "uq_conversations_active_course_key" not in conversation_indexes:
        op.create_index(
            "uq_conversations_active_course_key",
            "conversations",
            ["active_course_key"],
            unique=True,
        )

    message_columns = {column["name"] for column in inspector.get_columns("messages")}
    if "attachment_encrypted" not in message_columns:
        op.add_column("messages", sa.Column("attachment_encrypted", sa.Text(), nullable=True))

    if "course_homework_entries" not in tables:
        op.create_table(
            "course_homework_entries",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("conversation_id", sa.String(length=36), nullable=False),
            sa.Column("participant_id", sa.String(length=36), nullable=False),
            sa.Column("lesson_id", sa.String(length=40), nullable=False),
            sa.Column("payload_encrypted", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["participant_id"], ["participants.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_course_homework_entries_conversation_id",
            "course_homework_entries",
            ["conversation_id"],
            unique=False,
        )
        op.create_index(
            "ix_course_homework_entries_participant_id",
            "course_homework_entries",
            ["participant_id"],
            unique=False,
        )
        op.create_index(
            "ix_course_homework_entries_lesson_id",
            "course_homework_entries",
            ["lesson_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "course_homework_entries" in tables:
        op.drop_index("ix_course_homework_entries_lesson_id", table_name="course_homework_entries")
        op.drop_index("ix_course_homework_entries_participant_id", table_name="course_homework_entries")
        op.drop_index("ix_course_homework_entries_conversation_id", table_name="course_homework_entries")
        op.drop_table("course_homework_entries")
    message_columns = {column["name"] for column in sa.inspect(bind).get_columns("messages")}
    if "attachment_encrypted" in message_columns:
        op.drop_column("messages", "attachment_encrypted")
    conversation_indexes = {index["name"] for index in sa.inspect(bind).get_indexes("conversations")}
    if "uq_conversations_active_course_key" in conversation_indexes:
        op.drop_index("uq_conversations_active_course_key", table_name="conversations")
    conversation_columns = {column["name"] for column in sa.inspect(bind).get_columns("conversations")}
    if "active_course_key" in conversation_columns:
        op.drop_column("conversations", "active_course_key")
