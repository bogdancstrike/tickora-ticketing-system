"""add ticket_metadatas table

Revision ID: 0004_ticket_metadata
Revises: 0003_dashboard_mvs
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004_ticket_metadata"
down_revision: Union[str, None] = "0003_dashboard_mvs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_metadatas",
        sa.Column("id", pg.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticket_id", pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("label", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_ticket_metadata_ticket", "ticket_metadatas", ["ticket_id"])
    op.create_index("idx_ticket_metadata_key", "ticket_metadatas", ["key"])
    op.create_index("idx_ticket_metadata_ticket_key", "ticket_metadatas", ["ticket_id", "key"], unique=True)


def downgrade() -> None:
    op.drop_table("ticket_metadatas")
