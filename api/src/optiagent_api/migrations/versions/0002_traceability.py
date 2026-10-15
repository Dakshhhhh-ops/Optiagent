"""Store each project's requirement traceability and formulation status.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("traceability", sa.JSON()))
        batch.add_column(sa.Column("formulation_status", sa.String(32)))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("formulation_status")
        batch.drop_column("traceability")
