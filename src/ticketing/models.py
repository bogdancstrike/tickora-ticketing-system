"""Ticketing ORM — mirrors BRD §16. SQLAlchemy 2.x typed mappings."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.common.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Reference tables ─────────────────────────────────────────────────────────

class Sector(Base):
    __tablename__ = "sectors"

    id:          Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    code:        Mapped[str]      = mapped_column(String(50), unique=True, nullable=False)
    name:        Mapped[str]      = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active:   Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True)
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class SectorMembership(Base):
    __tablename__ = "sector_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "sector_id", "membership_role", name="uq_sector_membership"),
        Index("idx_sector_memberships_user",   "user_id"),
        Index("idx_sector_memberships_sector", "sector_id"),
        Index("idx_sector_memberships_role",   "sector_id", "membership_role"),
    )

    id:                Mapped[str]  = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id:           Mapped[str]  = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    sector_id:         Mapped[str]  = mapped_column(UUID(as_uuid=False), ForeignKey("sectors.id"), nullable=False)
    membership_role:   Mapped[str]  = mapped_column(String(50), nullable=False)  # member | chief
    is_active:         Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at:        Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:        Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        Index("idx_categories_code", "code", unique=True),
    )

    id:          Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    code:        Mapped[str]      = mapped_column(String(50), nullable=False, unique=True)
    name:        Mapped[str]      = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active:   Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    subcategories: Mapped[list["Subcategory"]] = relationship(
        "Subcategory", backref="category", cascade="all, delete-orphan",
        order_by="Subcategory.display_order, Subcategory.name",
    )


class Subcategory(Base):
    __tablename__ = "subcategories"
    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_subcategory_code"),
        Index("idx_subcategories_category", "category_id"),
    )

    id:             Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    category_id:    Mapped[str]      = mapped_column(UUID(as_uuid=False), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False)
    code:           Mapped[str]      = mapped_column(String(50), nullable=False)
    name:           Mapped[str]      = mapped_column(String(255), nullable=False)
    description:    Mapped[str | None] = mapped_column(Text)
    display_order:  Mapped[int]      = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    is_active:      Mapped[bool]     = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    fields: Mapped[list["SubcategoryFieldDefinition"]] = relationship(
        "SubcategoryFieldDefinition", backref="subcategory", cascade="all, delete-orphan",
        order_by="SubcategoryFieldDefinition.display_order, SubcategoryFieldDefinition.label",
    )


class SubcategoryFieldDefinition(Base):
    __tablename__ = "subcategory_field_definitions"
    __table_args__ = (
        UniqueConstraint("subcategory_id", "key", name="uq_subcategory_field_key"),
        Index("idx_subcategory_fields_subcategory", "subcategory_id"),
    )

    id:             Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    subcategory_id: Mapped[str]      = mapped_column(UUID(as_uuid=False), ForeignKey("subcategories.id", ondelete="CASCADE"), nullable=False)
    key:            Mapped[str]      = mapped_column(String(100), nullable=False)
    label:          Mapped[str]      = mapped_column(String(255), nullable=False)
    value_type:     Mapped[str]      = mapped_column(String(20), nullable=False, default="string", server_default="string")
    options:        Mapped[list[str] | None] = mapped_column(JSONB)
    is_required:    Mapped[bool]     = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    display_order:  Mapped[int]      = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    description:    Mapped[str | None] = mapped_column(Text)
    created_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:     Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class Beneficiary(Base):
    __tablename__ = "beneficiaries"
    __table_args__ = (
        Index("idx_beneficiaries_type",    "beneficiary_type"),
        Index("idx_beneficiaries_email",   "email"),
        Index("idx_beneficiaries_user_id", "user_id"),
        Index("idx_beneficiaries_org",     "organization_name"),
    )

    id:               Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    beneficiary_type: Mapped[str]      = mapped_column(String(50), nullable=False)  # internal | external

    user_id:           Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))

    first_name:        Mapped[str | None] = mapped_column(String(255))
    last_name:         Mapped[str | None] = mapped_column(String(255))
    email:             Mapped[str | None] = mapped_column(String(255))
    phone:             Mapped[str | None] = mapped_column(String(50))
    organization_name: Mapped[str | None] = mapped_column(String(255))
    external_identifier: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


# ── Tickets ──────────────────────────────────────────────────────────────────

class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("idx_tickets_status",            "status"),
        Index("idx_tickets_priority",          "priority"),
        Index("idx_tickets_category_id",       "category_id"),
        Index("idx_tickets_subcategory_id",    "subcategory_id"),
        Index("idx_tickets_beneficiary_type",  "beneficiary_type"),
        Index("idx_tickets_current_sector_status", "current_sector_id", "status"),
        Index("idx_tickets_assignee_status",   "assignee_user_id", "status"),
        Index("idx_tickets_created_by_user",   "created_by_user_id"),
        Index("idx_tickets_beneficiary",       "beneficiary_id"),
        Index("idx_tickets_created_at",        "created_at"),
        Index("idx_tickets_updated_at",        "updated_at"),
        Index("idx_tickets_done_at",           "done_at"),
        Index("idx_tickets_closed_at",         "closed_at"),
        Index("idx_tickets_requester_ip",      "requester_ip"),
        Index("idx_tickets_sector_created_at", "current_sector_id", "created_at"),
        Index("idx_tickets_sector_assignee_status",
              "current_sector_id", "assignee_user_id", "status"),
    )

    id:           Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ticket_code:  Mapped[str]      = mapped_column(String(50), unique=True, nullable=False)

    beneficiary_id:   Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("beneficiaries.id"))
    beneficiary_type: Mapped[str]        = mapped_column(String(50), nullable=False)

    created_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))

    requester_first_name:  Mapped[str | None] = mapped_column(String(255))
    requester_last_name:   Mapped[str | None] = mapped_column(String(255))
    requester_email:       Mapped[str | None] = mapped_column(String(255))
    requester_phone:       Mapped[str | None] = mapped_column(String(50))
    requester_organization: Mapped[str | None] = mapped_column(String(255))

    requester_ip: Mapped[str | None] = mapped_column(INET)
    source_ip:    Mapped[str | None] = mapped_column(INET)
    user_agent:   Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False))

    suggested_sector_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("sectors.id"))
    current_sector_id:   Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("sectors.id"))

    assignee_user_id:             Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    last_active_assignee_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))

    title:      Mapped[str | None] = mapped_column(String(500))
    txt:        Mapped[str]        = mapped_column(Text, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text)

    category_id:    Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("categories.id", ondelete="SET NULL"))
    subcategory_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("subcategories.id", ondelete="SET NULL"))
    priority: Mapped[str]        = mapped_column(String(50), nullable=False, default="medium")
    status:   Mapped[str]        = mapped_column(String(50), nullable=False, default="pending")

    assigned_at:        Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sector_assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_response_at:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at:            Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at:          Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reopened_at:        Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reopened_count: Mapped[int]    = mapped_column(Integer, nullable=False, default=0)

    is_deleted: Mapped[bool]     = mapped_column(Boolean, nullable=False, default=False)

    lock_version: Mapped[int]    = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


# ── Comments and attachments ────────────────────────────────────────────────

class TicketComment(Base):
    __tablename__ = "ticket_comments"
    __table_args__ = (
        Index("idx_ticket_comments_ticket_created", "ticket_id", "created_at"),
        Index("idx_ticket_comments_visibility",     "ticket_id", "visibility", "created_at"),
        Index("idx_ticket_comments_author",         "author_user_id", "created_at"),
    )

    id:        Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ticket_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id"), nullable=False)
    author_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))

    visibility:   Mapped[str] = mapped_column(String(20), nullable=False)  # public | private
    comment_type: Mapped[str] = mapped_column(String(50), nullable=False, default="user_comment")
    body:         Mapped[str] = mapped_column(Text, nullable=False)

    is_deleted:        Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    deleted_at:        Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"

    id:         Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ticket_id:  Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id"), nullable=False)
    comment_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("ticket_comments.id"), nullable=False)
    uploaded_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))

    file_name:    Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes:   Mapped[int] = mapped_column(BigInteger, nullable=False)

    storage_bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key:    Mapped[str] = mapped_column(Text, nullable=False)

    checksum_sha256:   Mapped[str | None] = mapped_column(String(128))
    is_scanned:        Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scan_result:       Mapped[str | None] = mapped_column(String(50))

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deleted_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    deleted_at:         Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationship to parent comment
    comment: Mapped[TicketComment] = relationship("TicketComment", backref="attachments", lazy="select")


# ── History tables ──────────────────────────────────────────────────────────

class TicketStatusHistory(Base):
    __tablename__ = "ticket_status_history"

    id:         Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ticket_id:  Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(50))
    new_status: Mapped[str]        = mapped_column(String(50), nullable=False)
    changed_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    reason:     Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TicketSectorHistory(Base):
    __tablename__ = "ticket_sector_history"

    id:         Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ticket_id:  Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id"), nullable=False)
    old_sector_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("sectors.id"))
    new_sector_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("sectors.id"))
    changed_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    reason:     Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TicketAssignmentHistory(Base):
    __tablename__ = "ticket_assignment_history"

    id:         Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ticket_id:  Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id"), nullable=False)
    old_assignee_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    new_assignee_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    changed_by_user_id:   Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    reason:     Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── Audit ───────────────────────────────────────────────────────────────────

# `AuditEvent` lives in `src.audit.models` since 2026-05-10. Keep a
# re-export here so existing `from src.ticketing.models import AuditEvent`
# imports keep working until callers migrate.
from src.audit.models import AuditEvent  # noqa: F401,E402


# ── Notifications + links ───────────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id:        Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id:   Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    ticket_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id"))

    type:  Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body:  Mapped[str | None] = mapped_column(Text)

    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    delivered_channels: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TicketLink(Base):
    __tablename__ = "ticket_links"
    __table_args__ = (
        UniqueConstraint("source_ticket_id", "target_ticket_id", "link_type", name="uq_ticket_link"),
    )

    id:               Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    source_ticket_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id"), nullable=False)
    target_ticket_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id"), nullable=False)
    link_type:        Mapped[str] = mapped_column(String(50), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TicketMetadata(Base):
    __tablename__ = "ticket_metadatas"
    __table_args__ = (
        Index("idx_ticket_metadata_ticket", "ticket_id"),
        Index("idx_ticket_metadata_key",    "key"),
        Index("idx_ticket_metadata_ticket_key", "ticket_id", "key", unique=True),
    )

    id:        Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ticket_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id"), nullable=False)

    key:       Mapped[str] = mapped_column(String(100), nullable=False)
    value:     Mapped[str] = mapped_column(Text, nullable=False)
    label:     Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class TicketSectorAssignment(Base):
    """Many-to-many sector routing."""
    __tablename__ = "ticket_sectors"
    __table_args__ = (
        Index("idx_ticket_sectors_ticket", "ticket_id"),
        Index("idx_ticket_sectors_sector", "sector_id"),
        Index("uq_ticket_sectors_ticket_sector", "ticket_id", "sector_id", unique=True),
    )

    id:               Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ticket_id:        Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    sector_id:        Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("sectors.id"), nullable=False)
    is_primary:       Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    added_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    added_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TicketAssignee(Base):
    """Many-to-many user assignment."""
    __tablename__ = "ticket_assignees"
    __table_args__ = (
        Index("idx_ticket_assignees_ticket", "ticket_id"),
        Index("idx_ticket_assignees_user",   "user_id"),
        Index("uq_ticket_assignees_ticket_user", "ticket_id", "user_id", unique=True),
    )

    id:               Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ticket_id:        Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    user_id:          Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    is_primary:       Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    added_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    added_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MetadataKeyDefinition(Base):
    """Catalogue of allowed metadata keys with optional fixed value lists."""
    __tablename__ = "metadata_key_definitions"

    key:         Mapped[str] = mapped_column(String(100), primary_key=True)
    label:       Mapped[str] = mapped_column(String(255), nullable=False)
    value_type:  Mapped[str] = mapped_column(String(20), nullable=False, server_default="string")
    options:     Mapped[list[str] | None] = mapped_column(JSONB)
    description: Mapped[str | None] = mapped_column(Text)
    is_active:   Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


# ── Watchers (Phase 7) ─────────────────────────────────────────────────────

class TicketEndorsement(Base):
    """Supplementary endorsement ("avizare suplimentară").

    Created by the active assignee while working a ticket. Targets either
    a specific avizator (``assigned_to_user_id`` set) or the avizator
    pool (``assigned_to_user_id IS NULL`` — any user with the
    ``tickora_avizator`` realm role can decide). A pending row blocks the
    ticket from moving to ``done`` / ``closed``; once a decision is
    recorded (approved or rejected, either is fine) the block lifts.
    """
    __tablename__ = "ticket_endorsements"
    __table_args__ = (
        Index("idx_endorsements_ticket",   "ticket_id"),
        Index("idx_endorsements_status",   "status"),
        Index("idx_endorsements_assignee", "assigned_to_user_id", "status"),
    )

    id:                   Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ticket_id:            Mapped[str]      = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    requested_by_user_id: Mapped[str]      = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    assigned_to_user_id:  Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    status:               Mapped[str]      = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    request_reason:       Mapped[str | None] = mapped_column(Text)
    decided_by_user_id:   Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    decision_reason:      Mapped[str | None] = mapped_column(Text)
    decided_at:           Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:           Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:           Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class TicketWatcher(Base):
    """Users who subscribed to a ticket without being assigned.

    A watcher gets the same notification fan-out as the requester /
    beneficiary on visible events (comments, status, sector changes).
    Private comments are still gated by `can_see_private_comments`, so
    subscribing doesn't grant new visibility — it just ensures the
    notification task picks the user up.

    Self-subscription only by default; admins can add/remove others.
    """
    __tablename__ = "ticket_watchers"
    __table_args__ = (
        Index("idx_ticket_watchers_ticket", "ticket_id"),
        Index("idx_ticket_watchers_user",   "user_id"),
        UniqueConstraint("ticket_id", "user_id", name="uq_ticket_watchers"),
    )

    id:                  Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    ticket_id:           Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    user_id:             Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    created_by_user_id:  Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    created_at:          Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ── Customizable Dashboards ────────────────────────────────────────────────

class CustomDashboard(Base):
    __tablename__ = "custom_dashboards"
    __table_args__ = (
        Index("idx_custom_dashboards_user", "owner_user_id"),
    )

    id:             Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    owner_user_id:  Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    title:          Mapped[str] = mapped_column(String(255), nullable=False)
    description:    Mapped[str | None] = mapped_column(Text)
    # `is_public` was deprecated in favour of explicit sharing (which we
    # haven't built yet). Keep the column mapped with a default so legacy
    # databases that still have it as NOT NULL accept new inserts. Older
    # rows keep whatever value they had. The drop-column migration
    # (`d5e9b1207f08`) is optional — when it runs, this attribute simply
    # stops appearing in INSERT statements.
    is_public:      Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    widgets: Mapped[list["DashboardWidget"]] = relationship("DashboardWidget", backref="dashboard", cascade="all, delete-orphan", order_by="DashboardWidget.created_at")


class DashboardWidget(Base):
    __tablename__ = "dashboard_widgets"

    id:           Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    dashboard_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("custom_dashboards.id", ondelete="CASCADE"), nullable=False)
    
    type:         Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., 'ticket_list', 'monitor_kpi', 'audit_log'
    title:        Mapped[str | None] = mapped_column(String(255))
    config:       Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    
    # Grid layout (compatible with react-grid-layout)
    x: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    y: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    w: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    h: Mapped[int] = mapped_column(Integer, nullable=False, default=4)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class UserDashboardSettings(Base):
    """User-specific settings for dashboards (favorite, default, etc)."""
    __tablename__ = "user_dashboard_settings"
    __table_args__ = (
        UniqueConstraint("user_id", "dashboard_id", name="uq_user_dash_settings"),
        Index("idx_user_dash_settings_user", "user_id"),
    )

    id:           Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id:      Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False)
    dashboard_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("custom_dashboards.id", ondelete="CASCADE"), nullable=False)
    
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default:  Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class WidgetDefinition(Base):
    __tablename__ = "widget_definitions"

    type:         Mapped[str]  = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str]  = mapped_column(String(255), nullable=False)
    description:  Mapped[str | None] = mapped_column(Text)
    is_active:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    icon:         Mapped[str | None] = mapped_column(String(50))
    required_roles: Mapped[list[str] | None] = mapped_column(JSONB)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class Snippet(Base):
    """Admin-authored procedure (markdown). See `snippet_audiences` for
    visibility scoping. Read-only for non-admins, filtered server-side."""
    __tablename__ = "snippets"
    __table_args__ = (
        Index("idx_snippets_title", "title"),
    )

    id:                 Mapped[str]      = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    title:              Mapped[str]      = mapped_column(String(255), nullable=False)
    body:               Mapped[str]      = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    created_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:         Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    audiences: Mapped[list["SnippetAudience"]] = relationship(
        "SnippetAudience", backref="snippet", cascade="all, delete-orphan",
    )


class SnippetAudience(Base):
    """One row per (kind, value) the snippet should be visible to. Zero
    rows on a snippet ⇒ everyone with an account can see it."""
    __tablename__ = "snippet_audiences"
    __table_args__ = (
        UniqueConstraint("snippet_id", "audience_kind", "audience_value", name="uq_snippet_audience"),
        Index("idx_snippet_audiences_snippet", "snippet_id"),
        Index("idx_snippet_audiences_kv", "audience_kind", "audience_value"),
    )

    id:             Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    snippet_id:     Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("snippets.id", ondelete="CASCADE"), nullable=False)
    # `sector` -> a sector code; `role` -> a Keycloak realm role name;
    # `beneficiary_type` -> `internal` or `external`.
    audience_kind:  Mapped[str] = mapped_column(String(20), nullable=False)
    audience_value: Mapped[str] = mapped_column(String(100), nullable=False)


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key:         Mapped[str]  = mapped_column(String(100), primary_key=True)
    value:       Mapped[dict] = mapped_column(JSONB, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
