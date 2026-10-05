"""add agent version tracking

Revision ID: f41c9e2a6d70
Revises: d3a8f4216e7b
Create Date: 2026-07-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f41c9e2a6d70"
down_revision: Union[str, None] = "d3a8f4216e7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("agent_version", sa.String(length=80), nullable=False, server_default="legacy-unversioned"),
    )
    op.add_column("conversations", sa.Column("agent_prompt_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_conversations_agent_version", "conversations", ["agent_version"], unique=False)
    op.add_column("turn_events", sa.Column("agent_version", sa.String(length=80), nullable=True))
    op.add_column("turn_events", sa.Column("agent_prompt_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_turn_events_agent_version", "turn_events", ["agent_version"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_turn_events_agent_version", table_name="turn_events")
    op.drop_column("turn_events", "agent_prompt_hash")
    op.drop_column("turn_events", "agent_version")
    op.drop_index("ix_conversations_agent_version", table_name="conversations")
    op.drop_column("conversations", "agent_prompt_hash")
    op.drop_column("conversations", "agent_version")
