"""fix orphan search vector trigger

Revision ID: 55b530c77125
Revises: 20260511_five_status_workflow
Create Date: 2026-05-11 21:05:57.198472
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '55b530c77125'
down_revision: Union[str, None] = '20260511_five_status_workflow'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the trigger with the correct name
    op.execute("DROP TRIGGER IF EXISTS trg_tickets_search_vector ON tickets")
    # Drop the function
    op.execute("DROP FUNCTION IF EXISTS tickets_search_vector_update CASCADE")


def downgrade() -> None:
    pass
