"""ticketing core: sectors, sector_memberships, beneficiaries, tickets,
comments, attachments, history tables, audit_events, notifications,
sla_policies, ticket_links

Revision ID: 0002_ticketing
Revises: 0001_users
Create Date: 2026-05-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002_ticketing"
down_revision: Union[str, None] = "0001_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_pk():
    return sa.Column("id", pg.UUID(as_uuid=False), primary_key=True)


def _ts():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    # ── sectors ────────────────────────────────────────────────────────────
    op.create_table(
        "sectors",
        _uuid_pk(),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts(),
    )

    # ── sector_memberships ─────────────────────────────────────────────────
    op.create_table(
        "sector_memberships",
        _uuid_pk(),
        sa.Column("user_id",   pg.UUID(as_uuid=False), sa.ForeignKey("users.id"),   nullable=False),
        sa.Column("sector_id", pg.UUID(as_uuid=False), sa.ForeignKey("sectors.id"), nullable=False),
        sa.Column("membership_role", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts(),
        sa.UniqueConstraint("user_id", "sector_id", "membership_role", name="uq_sector_membership"),
    )
    op.create_index("idx_sector_memberships_user",   "sector_memberships", ["user_id"])
    op.create_index("idx_sector_memberships_sector", "sector_memberships", ["sector_id"])
    op.create_index("idx_sector_memberships_role",   "sector_memberships", ["sector_id", "membership_role"])

    # ── beneficiaries ──────────────────────────────────────────────────────
    op.create_table(
        "beneficiaries",
        _uuid_pk(),
        sa.Column("beneficiary_type", sa.String(50), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("first_name", sa.String(255)),
        sa.Column("last_name",  sa.String(255)),
        sa.Column("email",      sa.String(255)),
        sa.Column("phone",      sa.String(50)),
        sa.Column("organization_name", sa.String(255)),
        sa.Column("external_identifier", sa.String(255)),
        *_ts(),
    )
    op.create_index("idx_beneficiaries_type",    "beneficiaries", ["beneficiary_type"])
    op.create_index("idx_beneficiaries_email",   "beneficiaries", ["email"])
    op.create_index("idx_beneficiaries_user_id", "beneficiaries", ["user_id"])
    op.create_index("idx_beneficiaries_org",     "beneficiaries", ["organization_name"])

    # ── tickets ────────────────────────────────────────────────────────────
    op.create_table(
        "tickets",
        _uuid_pk(),
        sa.Column("ticket_code", sa.String(50), nullable=False, unique=True),
        sa.Column("beneficiary_id",   pg.UUID(as_uuid=False), sa.ForeignKey("beneficiaries.id")),
        sa.Column("beneficiary_type", sa.String(50), nullable=False),
        sa.Column("created_by_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("requester_first_name",   sa.String(255)),
        sa.Column("requester_last_name",    sa.String(255)),
        sa.Column("requester_email",        sa.String(255)),
        sa.Column("requester_phone",        sa.String(50)),
        sa.Column("requester_organization", sa.String(255)),
        sa.Column("requester_ip", pg.INET),
        sa.Column("source_ip",    pg.INET),
        sa.Column("user_agent",   sa.Text),
        sa.Column("correlation_id", pg.UUID(as_uuid=False)),
        sa.Column("suggested_sector_id", pg.UUID(as_uuid=False), sa.ForeignKey("sectors.id")),
        sa.Column("current_sector_id",   pg.UUID(as_uuid=False), sa.ForeignKey("sectors.id")),
        sa.Column("assignee_user_id",             pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("last_active_assignee_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("title", sa.String(500)),
        sa.Column("txt", sa.Text, nullable=False),
        sa.Column("resolution", sa.Text),
        sa.Column("category", sa.String(100)),
        sa.Column("type",     sa.String(100)),
        sa.Column("priority", sa.String(50), nullable=False, server_default="medium"),
        sa.Column("status",   sa.String(50), nullable=False, server_default="pending"),
        sa.Column("assigned_at",        sa.DateTime(timezone=True)),
        sa.Column("sector_assigned_at", sa.DateTime(timezone=True)),
        sa.Column("first_response_at",  sa.DateTime(timezone=True)),
        sa.Column("done_at",   sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("reopened_at", sa.DateTime(timezone=True)),
        sa.Column("reopened_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("sla_due_at", sa.DateTime(timezone=True)),
        sa.Column("sla_status", sa.String(50), server_default="within_sla"),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("lock_version", sa.Integer, nullable=False, server_default="0"),
        *_ts(),
    )
    for name, cols in [
        ("idx_tickets_status",                "status"),
        ("idx_tickets_priority",              "priority"),
        ("idx_tickets_category",              "category"),
        ("idx_tickets_type",                  "type"),
        ("idx_tickets_beneficiary_type",      "beneficiary_type"),
        ("idx_tickets_created_by_user",       "created_by_user_id"),
        ("idx_tickets_beneficiary",           "beneficiary_id"),
        ("idx_tickets_created_at",            "created_at"),
        ("idx_tickets_updated_at",            "updated_at"),
        ("idx_tickets_done_at",               "done_at"),
        ("idx_tickets_closed_at",             "closed_at"),
        ("idx_tickets_sla_due_at",            "sla_due_at"),
        ("idx_tickets_requester_ip",          "requester_ip"),
    ]:
        op.create_index(name, "tickets", [cols])
    op.create_index("idx_tickets_current_sector_status",  "tickets", ["current_sector_id", "status"])
    op.create_index("idx_tickets_assignee_status",        "tickets", ["assignee_user_id", "status"])
    op.create_index("idx_tickets_sector_created_at",      "tickets", ["current_sector_id", "created_at"])
    op.create_index("idx_tickets_sector_assignee_status", "tickets",
                    ["current_sector_id", "assignee_user_id", "status"])
    # Partial indexes for hot lists
    op.execute("""
        CREATE INDEX idx_tickets_active_by_sector
        ON tickets(current_sector_id, priority, created_at DESC)
        WHERE status IN ('pending','assigned_to_sector','in_progress','waiting_for_user','on_hold','reopened')
          AND is_deleted = false;
    """)
    op.execute("""
        CREATE INDEX idx_tickets_unassigned
        ON tickets(current_sector_id, created_at DESC)
        WHERE assignee_user_id IS NULL
          AND status IN ('pending','assigned_to_sector');
    """)
    op.execute("""
        CREATE INDEX idx_tickets_beneficiary_active
        ON tickets(beneficiary_id, created_at DESC)
        WHERE is_deleted = false;
    """)

    # FTS: search_vector column + GIN index + trigger
    op.execute("ALTER TABLE tickets ADD COLUMN search_vector tsvector")
    op.execute("""
        CREATE OR REPLACE FUNCTION tickets_search_vector_update() RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('simple', coalesce(NEW.ticket_code, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(NEW.title, '')),       'B') ||
                setweight(to_tsvector('simple', coalesce(NEW.txt, '')),         'C') ||
                setweight(to_tsvector('simple', coalesce(NEW.resolution, '')),  'C') ||
                setweight(to_tsvector('simple',
                    coalesce(NEW.requester_first_name,'') || ' ' ||
                    coalesce(NEW.requester_last_name, '') || ' ' ||
                    coalesce(NEW.requester_organization,'')
                ), 'B');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_tickets_search_vector
        BEFORE INSERT OR UPDATE ON tickets
        FOR EACH ROW EXECUTE FUNCTION tickets_search_vector_update();
    """)
    op.execute("CREATE INDEX idx_tickets_search_vector ON tickets USING gin(search_vector)")

    # ── ticket_comments ────────────────────────────────────────────────────
    op.create_table(
        "ticket_comments",
        _uuid_pk(),
        sa.Column("ticket_id",      pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("author_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("visibility",   sa.String(20), nullable=False),
        sa.Column("comment_type", sa.String(50), nullable=False, server_default="user_comment"),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("deleted_by_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *_ts(),
    )
    op.create_index("idx_ticket_comments_ticket_created", "ticket_comments", ["ticket_id", "created_at"])
    op.create_index("idx_ticket_comments_visibility",     "ticket_comments", ["ticket_id", "visibility", "created_at"])
    op.create_index("idx_ticket_comments_author",         "ticket_comments", ["author_user_id", "created_at"])

    # ── ticket_attachments ─────────────────────────────────────────────────
    op.create_table(
        "ticket_attachments",
        _uuid_pk(),
        sa.Column("ticket_id",  pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("comment_id", pg.UUID(as_uuid=False), sa.ForeignKey("ticket_comments.id")),
        sa.Column("uploaded_by_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(255)),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("storage_bucket", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="private"),
        sa.Column("checksum_sha256", sa.String(128)),
        sa.Column("is_scanned", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("scan_result", sa.String(50)),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("deleted_by_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── history tables ─────────────────────────────────────────────────────
    op.create_table(
        "ticket_status_history",
        _uuid_pk(),
        sa.Column("ticket_id",  pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("old_status", sa.String(50)),
        sa.Column("new_status", sa.String(50), nullable=False),
        sa.Column("changed_by_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "ticket_sector_history",
        _uuid_pk(),
        sa.Column("ticket_id",  pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("old_sector_id", pg.UUID(as_uuid=False), sa.ForeignKey("sectors.id")),
        sa.Column("new_sector_id", pg.UUID(as_uuid=False), sa.ForeignKey("sectors.id")),
        sa.Column("changed_by_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "ticket_assignment_history",
        _uuid_pk(),
        sa.Column("ticket_id",  pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("old_assignee_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("new_assignee_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("changed_by_user_id",   pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── audit_events (NOT partitioned in MVP-1; partitioning in Phase 8) ──
    op.create_table(
        "audit_events",
        _uuid_pk(),
        sa.Column("actor_user_id",          pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("actor_keycloak_subject", sa.String(255)),
        sa.Column("actor_username",         sa.String(255)),
        sa.Column("action",      sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id",   pg.UUID(as_uuid=False)),
        sa.Column("ticket_id",   pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id")),
        sa.Column("old_value", pg.JSONB),
        sa.Column("new_value", pg.JSONB),
        sa.Column("metadata",  pg.JSONB),
        sa.Column("request_ip", pg.INET),
        sa.Column("user_agent", sa.Text),
        sa.Column("correlation_id", pg.UUID(as_uuid=False)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_audit_events_ticket",      "audit_events", ["ticket_id", "created_at"])
    op.create_index("idx_audit_events_actor",       "audit_events", ["actor_user_id", "created_at"])
    op.create_index("idx_audit_events_action",      "audit_events", ["action", "created_at"])
    op.create_index("idx_audit_events_entity",      "audit_events", ["entity_type", "entity_id", "created_at"])
    op.create_index("idx_audit_events_created_at",  "audit_events", ["created_at"])
    op.create_index("idx_audit_events_correlation", "audit_events", ["correlation_id"])

    # ── notifications ──────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        _uuid_pk(),
        sa.Column("user_id",   pg.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ticket_id", pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id")),
        sa.Column("type",  sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body",  sa.Text),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("delivered_channels", pg.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── sla_policies ──────────────────────────────────────────────────────
    op.create_table(
        "sla_policies",
        _uuid_pk(),
        sa.Column("name",     sa.String(255), nullable=False),
        sa.Column("priority", sa.String(50),  nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("beneficiary_type", sa.String(50)),
        sa.Column("first_response_minutes", sa.Integer, nullable=False),
        sa.Column("resolution_minutes",     sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        *_ts(),
    )

    # ── ticket_links ───────────────────────────────────────────────────────
    op.create_table(
        "ticket_links",
        _uuid_pk(),
        sa.Column("source_ticket_id", pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("target_ticket_id", pg.UUID(as_uuid=False), sa.ForeignKey("tickets.id"), nullable=False),
        sa.Column("link_type", sa.String(50), nullable=False),
        sa.Column("created_by_user_id", pg.UUID(as_uuid=False), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_ticket_id", "target_ticket_id", "link_type", name="uq_ticket_link"),
    )


def downgrade() -> None:
    op.drop_table("ticket_links")
    op.drop_table("sla_policies")
    op.drop_table("notifications")
    op.drop_index("idx_audit_events_correlation", table_name="audit_events")
    op.drop_index("idx_audit_events_created_at",  table_name="audit_events")
    op.drop_index("idx_audit_events_entity",      table_name="audit_events")
    op.drop_index("idx_audit_events_action",      table_name="audit_events")
    op.drop_index("idx_audit_events_actor",       table_name="audit_events")
    op.drop_index("idx_audit_events_ticket",      table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("ticket_assignment_history")
    op.drop_table("ticket_sector_history")
    op.drop_table("ticket_status_history")
    op.drop_table("ticket_attachments")
    op.drop_index("idx_ticket_comments_author",         table_name="ticket_comments")
    op.drop_index("idx_ticket_comments_visibility",     table_name="ticket_comments")
    op.drop_index("idx_ticket_comments_ticket_created", table_name="ticket_comments")
    op.drop_table("ticket_comments")
    op.execute("DROP INDEX IF EXISTS idx_tickets_search_vector")
    op.execute("DROP TRIGGER IF EXISTS trg_tickets_search_vector ON tickets")
    op.execute("DROP FUNCTION IF EXISTS tickets_search_vector_update")
    op.execute("DROP INDEX IF EXISTS idx_tickets_beneficiary_active")
    op.execute("DROP INDEX IF EXISTS idx_tickets_unassigned")
    op.execute("DROP INDEX IF EXISTS idx_tickets_active_by_sector")
    op.drop_table("tickets")
    op.drop_index("idx_beneficiaries_org",     table_name="beneficiaries")
    op.drop_index("idx_beneficiaries_user_id", table_name="beneficiaries")
    op.drop_index("idx_beneficiaries_email",   table_name="beneficiaries")
    op.drop_index("idx_beneficiaries_type",    table_name="beneficiaries")
    op.drop_table("beneficiaries")
    op.drop_index("idx_sector_memberships_role",   table_name="sector_memberships")
    op.drop_index("idx_sector_memberships_sector", table_name="sector_memberships")
    op.drop_index("idx_sector_memberships_user",   table_name="sector_memberships")
    op.drop_table("sector_memberships")
    op.drop_table("sectors")
