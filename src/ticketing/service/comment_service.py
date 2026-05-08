"""Ticket comments with server-side visibility filtering."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.errors import BusinessRuleError, NotFoundError, PermissionDeniedError, ValidationError
from src.iam import rbac
from src.iam.models import User
from src.iam.principal import Principal
from src.ticketing import events
from src.ticketing.models import TicketComment
from src.ticketing.service import audit_service, ticket_service
from src.tasking.producer import publish

EDIT_WINDOW = timedelta(minutes=15)


def list_(db: Session, principal: Principal, ticket_id: str) -> list[TicketComment]:
    ticket = ticket_service.get(db, principal, ticket_id)
    stmt = select(TicketComment).where(
        TicketComment.ticket_id == ticket.id,
        TicketComment.is_deleted.is_(False),
    )
    if not rbac.can_see_private_comments(principal, ticket):
        stmt = stmt.where(TicketComment.visibility == "public")
    comments = list(db.scalars(stmt.order_by(TicketComment.created_at.asc(), TicketComment.id.asc())))

    # Hydrate author display name/email/username for the serializer.
    author_ids = {c.author_user_id for c in comments if c.author_user_id}
    if author_ids:
        rows = db.execute(
            select(User.id, User.username, User.email, User.first_name, User.last_name)
            .where(User.id.in_(author_ids))
        ).all()
        index = {uid: (uname, email, first, last) for uid, uname, email, first, last in rows}
        for c in comments:
            row = index.get(c.author_user_id)
            if row:
                uname, email, first, last = row
                full = " ".join([n for n in (first, last) if n]).strip()
                setattr(c, "_author_display", full or uname or email or "user")
                setattr(c, "_author_username", uname)
                setattr(c, "_author_email", email)
    return comments


def create(
    db: Session,
    principal: Principal,
    ticket_id: str,
    *,
    body: str,
    visibility: str,
) -> TicketComment:
    ticket = ticket_service.get(db, principal, ticket_id)
    body = (body or "").strip()
    if len(body) < 2:
        raise ValidationError("comment body must be at least 2 characters")
    if len(body) > 10000:
        raise ValidationError("comment body is too long")
    if visibility not in ("public", "private"):
        raise ValidationError("visibility must be public or private")
    if visibility == "private":
        allowed = rbac.can_post_private_comment(principal, ticket)
    else:
        allowed = rbac.can_post_public_comment(principal, ticket)
    if not allowed:
        audit_service.record(
            db,
            actor=principal,
            action=events.ACCESS_DENIED,
            entity_type="ticket",
            entity_id=ticket_id,
            ticket_id=ticket_id,
            metadata={"attempted_action": "comment.create", "visibility": visibility},
        )
        raise PermissionDeniedError("not allowed to post this comment")

    comment = TicketComment(
        ticket_id=ticket.id,
        author_user_id=principal.user_id,
        visibility=visibility,
        comment_type="user_comment",
        body=body,
    )
    db.add(comment)
    db.flush()
    audit_service.record(
        db,
        actor=principal,
        action=events.COMMENT_CREATED,
        entity_type="comment",
        entity_id=comment.id,
        ticket_id=ticket.id,
        new_value={"visibility": visibility, "body": body},
    )
    publish("notify_comment", {
        "ticket_id":    ticket.id,
        "comment_id":   comment.id,
        "actor_user_id": principal.user_id,
        "visibility":   visibility,
    })
    return comment


def _load_visible(db: Session, principal: Principal, comment_id: str) -> TicketComment:
    comment = db.get(TicketComment, comment_id)
    if comment is None or comment.is_deleted:
        raise NotFoundError("comment not found")
    ticket_service.get(db, principal, comment.ticket_id)
    return comment


def edit(db: Session, principal: Principal, comment_id: str, *, body: str) -> TicketComment:
    comment = _load_visible(db, principal, comment_id)
    if comment.author_user_id != principal.user_id and not principal.is_admin:
        raise PermissionDeniedError("only the author or admin can edit this comment")
    if not principal.is_admin and comment.created_at:
        cutoff = datetime.now(timezone.utc) - EDIT_WINDOW
        created_at = comment.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at < cutoff:
            raise BusinessRuleError("comment edit window has expired")
    body = (body or "").strip()
    if len(body) < 2:
        raise ValidationError("comment body must be at least 2 characters")

    old = comment.body
    comment.body = body
    db.flush()
    audit_service.record(
        db,
        actor=principal,
        action=events.COMMENT_EDITED,
        entity_type="comment",
        entity_id=comment.id,
        ticket_id=comment.ticket_id,
        old_value={"body": old},
        new_value={"body": body},
    )
    return comment


def delete(db: Session, principal: Principal, comment_id: str) -> TicketComment:
    comment = _load_visible(db, principal, comment_id)
    if comment.author_user_id != principal.user_id and not principal.is_admin:
        raise PermissionDeniedError("only the author or admin can delete this comment")
    comment.is_deleted = True
    comment.deleted_by_user_id = principal.user_id
    comment.deleted_at = datetime.now(timezone.utc)
    db.flush()
    audit_service.record(
        db,
        actor=principal,
        action=events.COMMENT_DELETED,
        entity_type="comment",
        entity_id=comment.id,
        ticket_id=comment.ticket_id,
        old_value={"visibility": comment.visibility, "body": comment.body},
    )
    return comment
