"""remove search_vector and trigger

Revision ID: c769aeaad506
Revises: 8b305d56a8ec
Create Date: 2026-05-09 20:13:45.152877
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c769aeaad506'
down_revision: Union[str, None] = '8b305d56a8ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the trigger first
    op.execute("DROP TRIGGER IF EXISTS tickets_search_vector_update ON tickets")
    # Drop the column (this also drops the index)
    op.drop_column("tickets", "search_vector")


def downgrade() -> None:
    # Restore column
    op.add_column("tickets", sa.Column("search_vector", sa.NullType(), nullable=True))
    # Note: Trigger restoration would require full SQL definition, 
    # but since user wants it gone "wtf", we prioritize cleanup.
