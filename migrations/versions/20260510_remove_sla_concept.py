"""remove SLA ticketing concept

Revision ID: 20260510_remove_sla
Revises: f48a2b1c93e0
Create Date: 2026-05-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260510_remove_sla"
down_revision: Union[str, None] = "f48a2b1c93e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tickets_sla_due_at")
    op.execute("DROP INDEX IF EXISTS idx_tickets_admin_sla_due_active")
    op.execute("DROP INDEX IF EXISTS idx_sla_policies_match")
    op.execute("DROP TABLE IF EXISTS sla_policies")
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS sla_due_at")
    op.execute("ALTER TABLE tickets DROP COLUMN IF EXISTS sla_status")


def downgrade() -> None:
    op.add_column("tickets", sa.Column("sla_status", sa.String(length=50), server_default="within_sla", nullable=True))
    op.add_column("tickets", sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("CREATE INDEX IF NOT EXISTS idx_tickets_sla_due_at ON tickets(sla_due_at)")
    op.create_table(
        "sla_policies",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("beneficiary_type", sa.String(length=50), nullable=True),
        sa.Column("first_response_minutes", sa.Integer(), nullable=False),
        sa.Column("resolution_minutes", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
