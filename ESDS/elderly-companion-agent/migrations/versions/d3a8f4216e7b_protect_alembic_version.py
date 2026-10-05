"""protect Alembic version table

Revision ID: d3a8f4216e7b
Revises: b91e83c2d4f0
Create Date: 2026-07-17
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d3a8f4216e7b"
down_revision: Union[str, None] = "b91e83c2d4f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "alembic_version" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "alembic_version" DISABLE ROW LEVEL SECURITY')
