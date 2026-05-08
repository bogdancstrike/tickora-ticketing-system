"""users

Revision ID: 0001_users
Revises:
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_users"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("keycloak_subject", sa.String(255), nullable=False, unique=True),
        sa.Column("username",   sa.String(255)),
        sa.Column("email",      sa.String(255)),
        sa.Column("first_name", sa.String(255)),
        sa.Column("last_name",  sa.String(255)),
        sa.Column("user_type",  sa.String(50), nullable=False, server_default="internal"),
        sa.Column("is_active",  sa.Boolean,    nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_users_keycloak_subject", "users", ["keycloak_subject"], unique=True)
    op.create_index("idx_users_email",            "users", ["email"])
    op.create_index("idx_users_username",         "users", ["username"])


def downgrade() -> None:
    op.drop_index("idx_users_username",        table_name="users")
    op.drop_index("idx_users_email",           table_name="users")
    op.drop_index("idx_users_keycloak_subject", table_name="users")
    op.drop_table("users")
