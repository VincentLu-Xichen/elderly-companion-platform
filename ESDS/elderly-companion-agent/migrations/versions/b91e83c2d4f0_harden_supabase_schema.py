"""harden Supabase schema

Revision ID: b91e83c2d4f0
Revises: 7c4f97a2b01e
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b91e83c2d4f0"
down_revision: Union[str, None] = "7c4f97a2b01e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APP_TABLES = (
    "admin_audit_logs",
    "participants",
    "consents",
    "conversations",
    "messages",
    "turn_events",
    "rate_limit_buckets",
)


def upgrade() -> None:
    op.create_index("ix_turn_events_user_message_id", "turn_events", ["user_message_id"], unique=False)
    op.create_index("ix_turn_events_assistant_message_id", "turn_events", ["assistant_message_id"], unique=False)
    if op.get_bind().dialect.name == "postgresql":
        for table_name in APP_TABLES:
            op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table_name in APP_TABLES:
            op.execute(f'ALTER TABLE "{table_name}" DISABLE ROW LEVEL SECURITY')
    op.drop_index("ix_turn_events_assistant_message_id", table_name="turn_events")
    op.drop_index("ix_turn_events_user_message_id", table_name="turn_events")
