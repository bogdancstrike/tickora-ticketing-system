"""add metadata_key_definitions table for configurable option lists

Revision ID: 0005_metadata_key_definitions
Revises: 0004_ticket_metadata
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision: str = "0005_metadata_key_definitions"
down_revision: Union[str, None] = "0004_ticket_metadata"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "metadata_key_definitions",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("value_type", sa.String(20), nullable=False, server_default="string"),
        # options is a JSONB array of allowed values; NULL = free text input
        sa.Column("options", pg.JSONB),
        sa.Column("description", sa.Text),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Seed a few defaults: some have option lists, some are free text.
    op.execute(
        """
        INSERT INTO metadata_key_definitions (key, label, value_type, options, description) VALUES
          ('importance',   'Importance Level', 'enum',   '["1","2","3","4","5"]'::jsonb, '1 = trivial, 5 = mission critical'),
          ('impact_range', 'Impact Range',     'enum',   '["individual","team","department","organization"]'::jsonb, NULL),
          ('platform',     'Target Platform',  'enum',   '["web","mobile","desktop","backend","infrastructure"]'::jsonb, NULL),
          ('environment',  'Environment',      'enum',   '["production","staging","development","test"]'::jsonb, NULL),
          ('customer_id',  'Customer ID',      'string', NULL,                                                     'External customer / account reference'),
          ('order_ref',    'Order Reference',  'string', NULL,                                                     NULL),
          ('expected_at',  'Expected by',      'string', NULL,                                                     'Free-text date/expectation note')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("metadata_key_definitions")
