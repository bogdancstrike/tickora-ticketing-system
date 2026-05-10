"""drop is_public column from custom_dashboards

The flag was settable on write but never honored on read — there's no
"public dashboard" listing endpoint and the only list query filters by
`owner_user_id`. Rather than implement sharing-by-flag (which conflates
two access models), drop the column. If a sharing surface is needed in
the future, design it explicitly with the audit trail and RBAC in mind.

Revision ID: d5e9b1207f08
Revises: c4d8a72e1f5b
Create Date: 2026-05-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e9b1207f08"
down_revision: Union[str, None] = "c4d8a72e1f5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("custom_dashboards", "is_public")


def downgrade() -> None:
    # Restore as nullable=False with a default so existing rows pick up
    # `false` without an explicit backfill step.
    op.add_column(
        "custom_dashboards",
        sa.Column(
            "is_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Drop the server_default once the column is in place — the application
    # is responsible for setting the value going forward.
    op.alter_column("custom_dashboards", "is_public", server_default=None)
