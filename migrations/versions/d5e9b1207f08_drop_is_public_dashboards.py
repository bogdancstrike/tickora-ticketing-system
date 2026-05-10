"""drop is_public column from custom_dashboards (no-op as of 2026-05-10)

Originally this migration dropped the `is_public` column. We backed
that out: the column is harmless to keep, and dropping it created a
schema/model mismatch for already-deployed environments that hadn't
applied this revision yet.

We keep this revision in the chain (so already-bumped environments
don't see a missing revision) but the upgrade/downgrade are now no-ops.
The column lives on, defaulted to `false`, and the application no
longer reads or writes it.

Revision ID: d5e9b1207f08
Revises: c4d8a72e1f5b
Create Date: 2026-05-10
"""
from typing import Sequence, Union

revision: str = "d5e9b1207f08"
down_revision: Union[str, None] = "c4d8a72e1f5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Intentional no-op. Earlier drafts dropped `is_public` from
    # custom_dashboards; we kept the column to avoid an in-flight
    # schema/model mismatch. The application layer ignores the value.
    pass


def downgrade() -> None:
    pass
