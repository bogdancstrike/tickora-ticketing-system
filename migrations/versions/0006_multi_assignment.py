"""Multi-assignment: ticket_sectors + ticket_assignees join tables

Revision ID: 0006_multi_assignment
Revises: 0005_metadata_key_definitions
Create Date: 2026-05-08

Backfills the new tables from the existing single-valued columns. The
``current_sector_id`` / ``assignee_user_id`` fields stay on tickets as
the *primary* row — UIs and queries that don't care about multi-routing
keep working unchanged.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision: str = "0006_multi_assignment"
down_revision: Union[str, None] = "0005_metadata_key_definitions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_sectors",
        sa.Column("id", pg.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticket_id", pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sector_id", pg.UUID(as_uuid=False), sa.ForeignKey("sectors.id"), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("added_by_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_ticket_sectors_ticket", "ticket_sectors", ["ticket_id"])
    op.create_index("idx_ticket_sectors_sector", "ticket_sectors", ["sector_id"])
    op.create_index("uq_ticket_sectors_ticket_sector", "ticket_sectors",
                    ["ticket_id", "sector_id"], unique=True)

    op.create_table(
        "ticket_assignees",
        sa.Column("id", pg.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticket_id", pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id",   pg.UUID(as_uuid=False), sa.ForeignKey("users.id"),   nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("added_by_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_ticket_assignees_ticket", "ticket_assignees", ["ticket_id"])
    op.create_index("idx_ticket_assignees_user",   "ticket_assignees", ["user_id"])
    op.create_index("uq_ticket_assignees_ticket_user", "ticket_assignees",
                    ["ticket_id", "user_id"], unique=True)

    # Backfill from existing single-valued columns (gen_random_uuid is available
    # because pgcrypto / Postgres 13+ is in use elsewhere in the schema).
    op.execute(
        """
        INSERT INTO ticket_sectors (id, ticket_id, sector_id, is_primary, added_at)
        SELECT gen_random_uuid(), id, current_sector_id, true, COALESCE(sector_assigned_at, created_at)
        FROM tickets
        WHERE current_sector_id IS NOT NULL
        ON CONFLICT (ticket_id, sector_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO ticket_assignees (id, ticket_id, user_id, is_primary, added_at)
        SELECT gen_random_uuid(), id, assignee_user_id, true, COALESCE(assigned_at, created_at)
        FROM tickets
        WHERE assignee_user_id IS NOT NULL
        ON CONFLICT (ticket_id, user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("ticket_assignees")
    op.drop_table("ticket_sectors")
