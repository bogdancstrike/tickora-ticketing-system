"""ticket_endorsements — supplementary endorsement (avizare suplimentară)

A non-blocking second-opinion request the active assignee can fire off to
either a specific avizator user (`assigned_to_user_id` set) or the pool
(`assigned_to_user_id IS NULL` — visible to every `tickora_avizator`).

Ticket transition guards in `workflow_service` refuse `mark_done` and
`close` while any row here is `status='pending'`. A decision (`approved`
or `rejected`) is enough to unblock — the workflow doesn't care which
way the decision went, only that it was made.

Revision ID: 20260511_endorsements
Revises: 20260511_categories
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260511_endorsements"
down_revision: Union[str, None] = "20260511_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_endorsements",
        sa.Column("id",                   postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("ticket_id",            postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_to_user_id",  postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id")),
        sa.Column("status",               sa.String(20), nullable=False, server_default="pending"),
        sa.Column("request_reason",       sa.Text()),
        sa.Column("decided_by_user_id",   postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id")),
        sa.Column("decision_reason",      sa.Text()),
        sa.Column("decided_at",           sa.DateTime(timezone=True)),
        sa.Column("created_at",           sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",           sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_endorsements_ticket",     "ticket_endorsements", ["ticket_id"])
    op.create_index("idx_endorsements_status",     "ticket_endorsements", ["status"])
    op.create_index("idx_endorsements_assignee",   "ticket_endorsements", ["assigned_to_user_id", "status"])
    op.create_index("idx_endorsements_ticket_pend", "ticket_endorsements",
                    ["ticket_id"],
                    postgresql_where=sa.text("status = 'pending'"))


def downgrade() -> None:
    op.drop_index("idx_endorsements_ticket_pend", table_name="ticket_endorsements")
    op.drop_index("idx_endorsements_assignee",    table_name="ticket_endorsements")
    op.drop_index("idx_endorsements_status",      table_name="ticket_endorsements")
    op.drop_index("idx_endorsements_ticket",      table_name="ticket_endorsements")
    op.drop_table("ticket_endorsements")
