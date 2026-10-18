"""Typed adoption status for personal-disclosure boundaries."""
from alembic import op
import sqlalchemy as sa

revision = "f83a912be504"
down_revision = "e72f981ad403"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("interaction_reflections", sa.Column("memory_kind", sa.String(30), nullable=False, server_default="interaction_style"))
    op.add_column("interaction_reflections", sa.Column("status", sa.String(20), nullable=False, server_default="active"))
    op.create_index("ix_interaction_reflections_memory_kind", "interaction_reflections", ["memory_kind"])


def downgrade():
    op.drop_index("ix_interaction_reflections_memory_kind", table_name="interaction_reflections")
    with op.batch_alter_table("interaction_reflections") as batch:
        batch.drop_column("status")
        batch.drop_column("memory_kind")
