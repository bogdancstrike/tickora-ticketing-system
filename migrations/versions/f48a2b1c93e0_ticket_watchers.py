"""ticket watchers

Backs the new `ticket_watchers` table — users who subscribed to a ticket
they're not assigned to. Notifications fan out to watchers on visible
events (comments, status changes, sector changes). Private events stay
gated by RBAC, so subscribing doesn't grant new visibility.

Revision ID: f48a2b1c93e0
Revises: e7b34cd9f211
Create Date: 2026-05-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f48a2b1c93e0"
down_revision: Union[str, None] = "e7b34cd9f211"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_watchers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("ticket_id", "user_id", name="uq_ticket_watchers"),
    )
    op.create_index("idx_ticket_watchers_ticket", "ticket_watchers", ["ticket_id"])
    op.create_index("idx_ticket_watchers_user",   "ticket_watchers", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_ticket_watchers_user",   table_name="ticket_watchers")
    op.drop_index("idx_ticket_watchers_ticket", table_name="ticket_watchers")
    op.drop_table("ticket_watchers")
