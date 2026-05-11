"""categories + subcategories + dynamic field definitions

Introduces a structured 2-level taxonomy for ticket classification:

- `categories(id, code, name, description, is_active)` — top-level.
- `subcategories(id, category_id, code, name, description, display_order,
   is_active)` — children with a unique `(category_id, code)`.
- `subcategory_field_definitions(id, subcategory_id, key, label,
   value_type, options jsonb, is_required, display_order)` — per-subcategory
   dynamic metadata fields surfaced on the create-ticket form.

Tickets gain `category_id` + `subcategory_id` FKs. The previous free-text
`tickets.category` and `tickets.type` columns are dropped — the project is
in development mode and the user explicitly accepted breaking changes.

Revision ID: 20260511_categories
Revises: 20260510_remove_sla
Create Date: 2026-05-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260511_categories"
down_revision: Union[str, None] = "20260510_remove_sla"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id",          postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("code",        sa.String(50), nullable=False, unique=True),
        sa.Column("name",        sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active",   sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",  sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_categories_code", "categories", ["code"], unique=True)

    op.create_table(
        "subcategories",
        sa.Column("id",            postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("category_id",   postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code",          sa.String(50), nullable=False),
        sa.Column("name",          sa.String(255), nullable=False),
        sa.Column("description",   sa.Text()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active",     sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at",    sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",    sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("category_id", "code", name="uq_subcategory_code"),
    )
    op.create_index("idx_subcategories_category", "subcategories", ["category_id"])

    op.create_table(
        "subcategory_field_definitions",
        sa.Column("id",             postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("subcategory_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("subcategories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key",            sa.String(100), nullable=False),
        sa.Column("label",          sa.String(255), nullable=False),
        sa.Column("value_type",     sa.String(20),  nullable=False, server_default="string"),
        sa.Column("options",        postgresql.JSONB()),
        sa.Column("is_required",    sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("display_order",  sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("description",    sa.Text()),
        sa.Column("created_at",     sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",     sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("subcategory_id", "key", name="uq_subcategory_field_key"),
    )
    op.create_index("idx_subcategory_fields_subcategory",
                    "subcategory_field_definitions", ["subcategory_id"])

    # tickets: drop the old free-text columns and add the FKs.
    op.add_column("tickets",
        sa.Column("category_id",    postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("categories.id", ondelete="SET NULL")))
    op.add_column("tickets",
        sa.Column("subcategory_id", postgresql.UUID(as_uuid=False),
                  sa.ForeignKey("subcategories.id", ondelete="SET NULL")))
    op.create_index("idx_tickets_category_id",    "tickets", ["category_id"])
    op.create_index("idx_tickets_subcategory_id", "tickets", ["subcategory_id"])
    op.drop_index("idx_tickets_category", table_name="tickets")
    op.drop_index("idx_tickets_type",     table_name="tickets")
    op.drop_column("tickets", "category")
    op.drop_column("tickets", "type")


def downgrade() -> None:
    op.add_column("tickets", sa.Column("type",     sa.String(100)))
    op.add_column("tickets", sa.Column("category", sa.String(100)))
    op.create_index("idx_tickets_type",     "tickets", ["type"])
    op.create_index("idx_tickets_category", "tickets", ["category"])
    op.drop_index("idx_tickets_subcategory_id", table_name="tickets")
    op.drop_index("idx_tickets_category_id",    table_name="tickets")
    op.drop_column("tickets", "subcategory_id")
    op.drop_column("tickets", "category_id")

    op.drop_index("idx_subcategory_fields_subcategory", table_name="subcategory_field_definitions")
    op.drop_table("subcategory_field_definitions")
    op.drop_index("idx_subcategories_category", table_name="subcategories")
    op.drop_table("subcategories")
    op.drop_index("idx_categories_code", table_name="categories")
    op.drop_table("categories")
