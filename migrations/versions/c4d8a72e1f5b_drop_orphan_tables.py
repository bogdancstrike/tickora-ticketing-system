"""drop orphan tables and materialized views

Removes:
* `dashboard_shares` — model existed but no service code ever read or wrote
  rows. See SECURITY_REVIEW.md §D for the rationale.
* `mv_dashboard_global_kpis`, `mv_dashboard_sector_kpis` — materialized views
  defined in `0003_dashboard_mvs`. Runtime monitor code now uses live
  aggregates with a Redis cache, so the MVs only consume disk and refresh
  cycles.

Rolling back this migration recreates the dashboard_shares schema for
forward compatibility, but the materialized views are *not* recreated —
restoring them requires re-running the full DDL from `0003_dashboard_mvs`,
which is out of scope for a rollback.

Revision ID: c4d8a72e1f5b
Revises: 9a1f3e0c2d10
Create Date: 2026-05-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c4d8a72e1f5b"
down_revision: Union[str, None] = "9a1f3e0c2d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Drop orphan dashboard_shares table ────────────────────────────────
    # Indexes/constraints are dropped implicitly by DROP TABLE.
    op.execute("DROP TABLE IF EXISTS dashboard_shares CASCADE")

    # ── Drop unused dashboard materialized views ──────────────────────────
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_dashboard_sector_kpis CASCADE")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_dashboard_global_kpis CASCADE")


def downgrade() -> None:
    # Recreate dashboard_shares so consumers that pinned to this revision
    # still see the table on rollback. The MVs are intentionally NOT
    # recreated — the original DDL lives in `0003_dashboard_mvs`.
    op.create_table(
        "dashboard_shares",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("custom_dashboards.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("target_user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("target_sector_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("sectors.id"), nullable=True),
        sa.Column("shared_by_user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("dashboard_id", "target_user_id", name="uq_dash_share_user"),
        sa.UniqueConstraint("dashboard_id", "target_sector_id", name="uq_dash_share_sector"),
    )
    op.create_index("idx_dashboard_shares_dashboard", "dashboard_shares", ["dashboard_id"])
    op.create_index("idx_dashboard_shares_user",      "dashboard_shares", ["target_user_id"])
    op.create_index("idx_dashboard_shares_sector",    "dashboard_shares", ["target_sector_id"])
