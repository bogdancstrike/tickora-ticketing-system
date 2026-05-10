"""tasks lifecycle table

Backs the new `src.tasking.models.Task` ORM. Every call to
`producer.publish(...)` now writes a `pending` row; the consumer flips it
through `running` → `completed` / `failed`. See `docs/architecture.md` for
the full lifecycle.

Revision ID: e7b34cd9f211
Revises: d5e9b1207f08
Create Date: 2026-05-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e7b34cd9f211"
down_revision: Union[str, None] = "d5e9b1207f08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("task_name", sa.String(length=120), nullable=False),
        sa.Column("topic",     sa.String(length=120), nullable=True),
        sa.Column("status",    sa.String(length=20),  nullable=False, server_default="pending"),
        sa.Column("payload",   postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("attempts",  sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.func.now(), nullable=False),
        sa.Column("started_at",        sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at",      sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_tasks_status_created",     "tasks", ["status", "created_at"])
    op.create_index("idx_tasks_task_name_created",  "tasks", ["task_name", "created_at"])
    # Partial index for active rows — the only ones operators care about.
    op.execute(
        """
        CREATE INDEX idx_tasks_active
        ON tasks(status, last_heartbeat_at)
        WHERE status IN ('pending','running')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_tasks_active")
    op.drop_index("idx_tasks_task_name_created", table_name="tasks")
    op.drop_index("idx_tasks_status_created",    table_name="tasks")
    op.drop_table("tasks")
