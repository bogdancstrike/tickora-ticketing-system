"""phase 9 performance indexes for million-row ticket scale

Adds covering indexes that target the hot list/sort/filter paths exercised on
TicketsPage and ReviewTicketsPage. Each index is partial on `is_deleted = false`
because every list query enforces that predicate, so the partial index is much
smaller and faster than a full one.

Revision ID: 9a1f3e0c2d10
Revises: 2b65909b3b0c
Create Date: 2026-05-09
"""
from typing import Sequence, Union

from alembic import op

revision: str = "9a1f3e0c2d10"
down_revision: Union[str, None] = "2b65909b3b0c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES = [
    # Default landing query: WHERE is_deleted = false ORDER BY created_at DESC.
    # The existing idx_tickets_created_at is non-partial; a partial keeps the
    # leaf pages tight and lets PG skip the is_deleted check.
    (
        "idx_tickets_active_created_at",
        """
        CREATE INDEX IF NOT EXISTS idx_tickets_active_created_at
        ON tickets(created_at DESC, id DESC)
        WHERE is_deleted = false
        """,
    ),
    # Status-filtered list (TicketsPage status filter, ReviewTicketsPage queues).
    (
        "idx_tickets_active_status_created",
        """
        CREATE INDEX IF NOT EXISTS idx_tickets_active_status_created
        ON tickets(status, created_at DESC, id DESC)
        WHERE is_deleted = false
        """,
    ),
    # Priority-filtered list (DashboardPage by-priority, TicketsPage filter).
    (
        "idx_tickets_active_priority_created",
        """
        CREATE INDEX IF NOT EXISTS idx_tickets_active_priority_created
        ON tickets(priority, created_at DESC, id DESC)
        WHERE is_deleted = false
        """,
    ),
    # "My tickets" — beneficiaries/creators land here. Visibility predicate
    # joins `created_by_user_id` against the principal.
    (
        "idx_tickets_active_creator_created",
        """
        CREATE INDEX IF NOT EXISTS idx_tickets_active_creator_created
        ON tickets(created_by_user_id, created_at DESC)
        WHERE is_deleted = false AND created_by_user_id IS NOT NULL
        """,
    ),
    # Sector-scoped queues for chiefs/members. Pairs sector with the sort key
    # so PG can return rows in order without a sort step.
    (
        "idx_tickets_active_sector_created",
        """
        CREATE INDEX IF NOT EXISTS idx_tickets_active_sector_created
        ON tickets(current_sector_id, created_at DESC, id DESC)
        WHERE is_deleted = false AND current_sector_id IS NOT NULL
        """,
    ),
    # Multi-sector assignment lookups (ticket_sectors join in visibility filter).
    (
        "idx_ticket_sectors_sector_ticket",
        """
        CREATE INDEX IF NOT EXISTS idx_ticket_sectors_sector_ticket
        ON ticket_sectors(sector_id, ticket_id)
        """,
    ),
    # Multi-assignee join (assignee filter + visibility for "my work").
    (
        "idx_ticket_assignees_user_ticket",
        """
        CREATE INDEX IF NOT EXISTS idx_ticket_assignees_user_ticket
        ON ticket_assignees(user_id, ticket_id)
        """,
    ),
    # Audit-by-actor recency (Profile / activity feeds).
    (
        "idx_audit_events_actor_recent",
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_actor_recent
        ON audit_events(actor_user_id, created_at DESC)
        WHERE actor_user_id IS NOT NULL
        """,
    ),
    # Comments authored-by-user feed.
    (
        "idx_ticket_comments_author_recent",
        """
        CREATE INDEX IF NOT EXISTS idx_ticket_comments_author_recent
        ON ticket_comments(author_user_id, created_at DESC)
        WHERE author_user_id IS NOT NULL
        """,
    ),
]


def upgrade() -> None:
    for _, sql in _INDEXES:
        op.execute(sql)


def downgrade() -> None:
    for name, _ in reversed(_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
