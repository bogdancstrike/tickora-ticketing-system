"""Ticket attachment metadata and presigned URL flow."""
from __future__ import annotations

import posixpath
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.config import Config
from src.core import object_storage
from src.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from src.iam import rbac
from src.iam.principal import Principal
from src.ticketing import events
from src.ticketing.models import TicketAttachment
from src.ticketing.service import audit_service, ticket_service

SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_filename(name: str) -> str:
    cleaned = SAFE_NAME.sub("_", (name or "").strip()).strip("._")
    if not cleaned:
        raise ValidationError("file_name is required")
    return cleaned[:240]


def _storage_key(ticket_id: str, file_name: str) -> str:
    return posixpath.join("tickets", ticket_id, str(uuid.uuid4()), _safe_filename(file_name))


def _validate_visibility(value: str) -> str:
    if value not in ("public", "private"):
        raise ValidationError("visibility must be public or private")
    return value


def request_upload_url(
    db: Session,
    principal: Principal,
    ticket_id: str,
    *,
    file_name: str,
    content_type: str | None,
    size_bytes: int,
    visibility: str = "private",
) -> dict:
    ticket = ticket_service.get(db, principal, ticket_id)
    if not rbac.can_upload_attachment(principal, ticket):
        raise PermissionDeniedError("not allowed to upload attachments")
    _validate_visibility(visibility)
    file_name = _safe_filename(file_name)
    if size_bytes <= 0:
        raise ValidationError("size_bytes must be positive")
    if size_bytes > Config.ATTACHMENT_MAX_SIZE_BYTES:
        raise ValidationError("attachment too large")

    object_storage.ensure_bucket(Config.S3_BUCKET_ATTACHMENTS)
    key = _storage_key(ticket.id, file_name)
    url = object_storage.presigned_put_url(
        Config.S3_BUCKET_ATTACHMENTS,
        key,
        content_type=content_type,
        expires=Config.ATTACHMENT_PRESIGNED_TTL,
    )
    return {
        "upload_url": url,
        "storage_bucket": Config.S3_BUCKET_ATTACHMENTS,
        "storage_key": key,
        "expires_in": Config.ATTACHMENT_PRESIGNED_TTL,
    }


def register(
    db: Session,
    principal: Principal,
    ticket_id: str,
    *,
    storage_key: str,
    file_name: str,
    size_bytes: int,
    content_type: str | None = None,
    checksum_sha256: str | None = None,
    visibility: str = "private",
    comment_id: str | None = None,
) -> TicketAttachment:
    ticket = ticket_service.get(db, principal, ticket_id)
    if not rbac.can_upload_attachment(principal, ticket):
        raise PermissionDeniedError("not allowed to register attachments")
    visibility = _validate_visibility(visibility)
    file_name = _safe_filename(file_name)
    if size_bytes <= 0:
        raise ValidationError("size_bytes must be positive")
    if size_bytes > Config.ATTACHMENT_MAX_SIZE_BYTES:
        raise ValidationError("attachment too large")
    if not storage_key.startswith(f"tickets/{ticket.id}/"):
        raise ValidationError("storage_key is not valid for this ticket")
    if not object_storage.object_exists(Config.S3_BUCKET_ATTACHMENTS, storage_key):
        raise ValidationError("uploaded object was not found")

    attachment = TicketAttachment(
        ticket_id=ticket.id,
        comment_id=comment_id,
        uploaded_by_user_id=principal.user_id,
        file_name=file_name,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_bucket=Config.S3_BUCKET_ATTACHMENTS,
        storage_key=storage_key,
        visibility=visibility,
        checksum_sha256=checksum_sha256,
        is_scanned=True,
        scan_result="clean",
    )
    db.add(attachment)
    db.flush()
    audit_service.record(
        db,
        actor=principal,
        action=events.ATTACHMENT_UPLOADED,
        entity_type="attachment",
        entity_id=attachment.id,
        ticket_id=ticket.id,
        new_value={"file_name": file_name, "visibility": visibility, "size_bytes": size_bytes},
    )
    return attachment


def list_(db: Session, principal: Principal, ticket_id: str) -> list[TicketAttachment]:
    ticket = ticket_service.get(db, principal, ticket_id)
    stmt = select(TicketAttachment).where(
        TicketAttachment.ticket_id == ticket.id,
        TicketAttachment.is_deleted.is_(False),
    )
    if not rbac.can_see_private_comments(principal, ticket):
        stmt = stmt.where(TicketAttachment.visibility == "public")
    return list(db.scalars(stmt.order_by(TicketAttachment.created_at.desc(), TicketAttachment.id.desc())))


def _load_authorized(db: Session, principal: Principal, attachment_id: str) -> tuple[TicketAttachment, object]:
    attachment = db.get(TicketAttachment, attachment_id)
    if attachment is None or attachment.is_deleted:
        raise NotFoundError("attachment not found")
    ticket = ticket_service.get(db, principal, attachment.ticket_id)
    if not rbac.can_download_attachment(principal, ticket, attachment.visibility):
        raise PermissionDeniedError("not allowed to access attachment")
    return attachment, ticket


def download_url(db: Session, principal: Principal, attachment_id: str) -> str:
    attachment, ticket = _load_authorized(db, principal, attachment_id)
    url = object_storage.presigned_get_url(
        attachment.storage_bucket,
        attachment.storage_key,
        expires=Config.ATTACHMENT_PRESIGNED_TTL,
    )
    audit_service.record(
        db,
        actor=principal,
        action=events.ATTACHMENT_DOWNLOADED,
        entity_type="attachment",
        entity_id=attachment.id,
        ticket_id=ticket.id,
        metadata={"file_name": attachment.file_name},
    )
    return url


def delete(db: Session, principal: Principal, attachment_id: str) -> TicketAttachment:
    attachment, ticket = _load_authorized(db, principal, attachment_id)
    if attachment.uploaded_by_user_id != principal.user_id and not rbac.can_modify_ticket(principal, ticket):
        raise PermissionDeniedError("not allowed to delete attachment")
    attachment.is_deleted = True
    attachment.deleted_by_user_id = principal.user_id
    attachment.deleted_at = datetime.now(timezone.utc)
    db.flush()
    audit_service.record(
        db,
        actor=principal,
        action=events.ATTACHMENT_DELETED,
        entity_type="attachment",
        entity_id=attachment.id,
        ticket_id=ticket.id,
        old_value={"file_name": attachment.file_name, "visibility": attachment.visibility},
    )
    return attachment
