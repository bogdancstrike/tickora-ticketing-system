"""dashboard materialized views for global and sector KPIs

Revision ID: 0003_dashboard_mvs
Revises: 0002_ticketing
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_dashboard_mvs"
down_revision: Union[str, None] = "0002_ticketing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # ── mv_dashboard_global_kpis ──────────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW mv_dashboard_global_kpis AS
        SELECT
            count(*) as total_tickets,
            sum(case when status IN ('pending', 'assigned_to_sector', 'in_progress', 'waiting_for_user', 'on_hold', 'reopened') then 1 else 0 end) as active_tickets,
            sum(case when created_at >= date_trunc('day', now()) then 1 else 0 end) as new_today,
            sum(case when closed_at >= date_trunc('day', now()) then 1 else 0 end) as closed_today,
            sum(case when sla_status = 'breached' then 1 else 0 end) as sla_breached,
            sum(case when reopened_count > 0 then 1 else 0 end) as reopened,
            avg(case when assigned_at IS NOT NULL then extract(epoch from (assigned_at - created_at))/60 else NULL end) as avg_assignment_minutes,
            avg(case when done_at IS NOT NULL then extract(epoch from (done_at - created_at))/60 else NULL end) as avg_resolution_minutes
        FROM tickets
        WHERE is_deleted = false
        WITH DATA;
    """)
    op.create_index("idx_mv_global_kpis_refresh", "mv_dashboard_global_kpis", ["total_tickets"], unique=False)

    # ── mv_dashboard_sector_kpis ──────────────────────────────────────────
    op.execute("""
        CREATE MATERIALIZED VIEW mv_dashboard_sector_kpis AS
        SELECT
            current_sector_id,
            count(*) as total,
            sum(case when status IN ('pending', 'assigned_to_sector', 'in_progress', 'waiting_for_user', 'on_hold', 'reopened') then 1 else 0 end) as active,
            sum(case when assignee_user_id IS NULL AND status IN ('pending', 'assigned_to_sector', 'in_progress', 'waiting_for_user', 'on_hold', 'reopened') then 1 else 0 end) as unassigned,
            sum(case when status IN ('done', 'closed') then 1 else 0 end) as done,
            sum(case when sla_status = 'breached' then 1 else 0 end) as sla_breached,
            sum(case when reopened_count > 0 then 1 else 0 end) as reopened,
            avg(case when done_at IS NOT NULL then extract(epoch from (done_at - created_at))/60 else NULL end) as avg_resolution_minutes
        FROM tickets
        WHERE is_deleted = false AND current_sector_id IS NOT NULL
        GROUP BY current_sector_id
        WITH DATA;
    """)
    op.create_index("idx_mv_sector_kpis_sector", "mv_dashboard_sector_kpis", ["current_sector_id"], unique=True)

def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_dashboard_sector_kpis")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_dashboard_global_kpis")
