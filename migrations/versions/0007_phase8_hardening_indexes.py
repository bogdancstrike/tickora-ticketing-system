"""phase 8 hardening indexes

Revision ID: 0007_phase8_hardening_indexes
Revises: 0006_multi_assignment
Create Date: 2026-05-09
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007_phase8_hardening_indexes"
down_revision: Union[str, None] = "0006_multi_assignment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tickets_admin_status_updated
        ON tickets(status, updated_at DESC, id DESC)
        WHERE is_deleted = false
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tickets_admin_sla_due_active
        ON tickets(sla_status, sla_due_at, priority, id)
        WHERE is_deleted = false
          AND status IN ('pending','assigned_to_sector','in_progress','reopened')
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tickets_requester_email_trgm
        ON tickets USING gin (requester_email gin_trgm_ops)
        WHERE requester_email IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_tickets_title_trgm
        ON tickets USING gin (title gin_trgm_ops)
        WHERE title IS NOT NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_audit_events_admin_recent
        ON audit_events(created_at DESC, action, entity_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_user_unread_recent
        ON notifications(user_id, is_read, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sla_policies_match
        ON sla_policies(priority, category, beneficiary_type, is_active)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_sector_memberships_active_sector_role_user
        ON sector_memberships(sector_id, membership_role, user_id)
        WHERE is_active = true
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_metadata_key_definitions_active
        ON metadata_key_definitions(is_active, key)
    """)


def downgrade() -> None:
    for index_name in [
        "idx_metadata_key_definitions_active",
        "idx_sector_memberships_active_sector_role_user",
        "idx_sla_policies_match",
        "idx_notifications_user_unread_recent",
        "idx_audit_events_admin_recent",
        "idx_tickets_title_trgm",
        "idx_tickets_requester_email_trgm",
        "idx_tickets_admin_sla_due_active",
        "idx_tickets_admin_status_updated",
    ]:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
