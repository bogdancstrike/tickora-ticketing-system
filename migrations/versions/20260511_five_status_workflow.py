"""normalize ticket workflow to five statuses

Revision ID: 20260511_five_status_workflow
Revises: 20260511_snippets
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260511_five_status_workflow"
down_revision: Union[str, None] = "20260511_snippets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE tickets SET status = 'done' WHERE status = 'closed'")
    op.execute("UPDATE tickets SET status = 'in_progress' WHERE status = 'reopened'")


def downgrade() -> None:
    # The old closed/reopened distinction cannot be reconstructed once rows
    # have been normalized.
    pass
