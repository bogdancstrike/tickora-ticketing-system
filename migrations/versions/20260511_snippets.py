"""snippets + snippet_audiences — operator-facing procedures

Each snippet is an admin-authored Markdown procedure. Audience rows
restrict who can see it: an empty audience set means "every authenticated
user". A row is `(audience_kind, audience_value)` where `audience_kind ∈
{sector, role, beneficiary_type}` — the snippet is visible if at least
one row matches the principal's sectors / realm roles / beneficiary type.

Revision ID: 20260511_snippets
Revises: 20260511_endorsements
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260511_snippets"
down_revision: Union[str, None] = "20260511_endorsements"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "snippets",
        sa.Column("id",                 postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("title",              sa.String(255), nullable=False),
        sa.Column("body",               sa.Text(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("users.id")),
        sa.Column("created_at",         sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",         sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_snippets_title", "snippets", ["title"])

    op.create_table(
        "snippet_audiences",
        sa.Column("id",             postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("snippet_id",     postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("snippets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("audience_kind",  sa.String(20), nullable=False),
        sa.Column("audience_value", sa.String(100), nullable=False),
        sa.UniqueConstraint("snippet_id", "audience_kind", "audience_value",
                            name="uq_snippet_audience"),
    )
    op.create_index("idx_snippet_audiences_snippet", "snippet_audiences", ["snippet_id"])
    op.create_index("idx_snippet_audiences_kv",      "snippet_audiences",
                    ["audience_kind", "audience_value"])


def downgrade() -> None:
    op.drop_index("idx_snippet_audiences_kv",      table_name="snippet_audiences")
    op.drop_index("idx_snippet_audiences_snippet", table_name="snippet_audiences")
    op.drop_table("snippet_audiences")
    op.drop_index("idx_snippets_title", table_name="snippets")
    op.drop_table("snippets")
