"""Independent encrypted interaction reflection memory."""
from alembic import op
import sqlalchemy as sa

revision = "e72f981ad403"
down_revision = "c82d1a4f907b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("interaction_reflections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("participant_id", sa.String(36), sa.ForeignKey("participants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_event_id", sa.String(36), sa.ForeignKey("turn_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lesson_id", sa.String(40), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("payload_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("turn_event_id", name="uq_interaction_reflection_event"))
    for column in ("participant_id", "conversation_id", "created_at"):
        op.create_index(f"ix_interaction_reflections_{column}", "interaction_reflections", [column])
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "interaction_reflections" ENABLE ROW LEVEL SECURITY')
        op.execute('REVOKE ALL ON TABLE "interaction_reflections" FROM anon, authenticated')


def downgrade():
    op.drop_table("interaction_reflections")
