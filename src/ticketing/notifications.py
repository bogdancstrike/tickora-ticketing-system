"""Notification handlers and delivery logic."""
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from framework.commons.logger import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.common.db import get_db, enqueue_after_commit
from src.config import Config
from src.iam.keycloak_admin import KeycloakAdminClient
from src.tasking.registry import register_task
from src.ticketing.models import Beneficiary, Notification, Ticket, TicketAssignee, SectorMembership, Sector
from src.iam.models import User as IAMUser

@register_task("notify_distributors")
def notify_distributors(payload: Dict[str, Any]):
    """
    Notify all distributors and admins about a new ticket.

    This task is typically triggered when a new ticket is created. It fetches all
    users with the 'tickora_admin' or 'tickora_distributor' roles from Keycloak,
    maps them to local users, and creates in-app notifications for each.

    Args:
        payload: Dictionary containing 'ticket_id'.
    """
    ticket_id = payload.get("ticket_id")
    with get_db() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            logger.warning("ticket not found for notification", extra={"ticket_id": ticket_id})
            return

        kc = KeycloakAdminClient.get()
        recipients_subjects = set()
        
        from src.iam.principal import ROLE_ADMIN, ROLE_DISTRIBUTOR
        for role in (ROLE_ADMIN, ROLE_DISTRIBUTOR):
            try:
                users = kc.get_users_by_role(role)
                for u in users:
                    # Keycloak returns 'id' for the subject/sub
                    if u.get("id"):
                        recipients_subjects.add(u["id"])
            except Exception as e:
                logger.warning("failed to fetch users for role", extra={"role": role, "error": str(e)})

        if not recipients_subjects:
            logger.info("no distributors or admins found to notify")
            return

        # Map Keycloak subjects to local user IDs
        users = db.scalars(
            select(IAMUser).where(IAMUser.keycloak_subject.in_(list(recipients_subjects)), IAMUser.is_active.is_(True))
        ).all()

        for user in users:
            _create_in_app_notification(
                db, 
                user_id=user.id,
                type="ticket_created",
                title="New Ticket Pending Triage",
                body=f"Ticket {ticket.ticket_code} has been created and needs review.",
                ticket_id=ticket.id
            )
        db.commit()

@register_task("notify_sector")
def notify_sector(payload: Dict[str, Any]):
    """Notify all members of a sector about a new assignment."""
    ticket_id = payload.get("ticket_id")
    sector_id = payload.get("sector_id")
    with get_db() as db:
        ticket = db.get(Ticket, ticket_id)
        sector = db.get(Sector, sector_id)
        if not ticket or not sector:
            return

        members = db.scalars(
            select(SectorMembership.user_id)
            .where(SectorMembership.sector_id == sector_id, SectorMembership.is_active.is_(True))
        ).all()

        for user_id in members:
            _create_in_app_notification(
                db,
                user_id=user_id,
                type="sector_assigned",
                title=f"New Ticket in {sector.code}",
                body=f"Ticket {ticket.ticket_code} has been assigned to your sector.",
                ticket_id=ticket.id
            )
        db.commit()

@register_task("notify_assignee")
def notify_assignee(payload: Dict[str, Any]):
    """Notify a specific user about a ticket assignment."""
    ticket_id = payload.get("ticket_id")
    user_id = payload.get("user_id")
    with get_db() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            return

        _create_in_app_notification(
            db,
            user_id=user_id,
            type="ticket_assigned",
            title="Ticket Assigned to You",
            body=f"Ticket {ticket.ticket_code} has been assigned to you.",
            ticket_id=ticket.id
        )
        db.commit()


@register_task("notify_ticket_event")
def notify_ticket_event(payload: Dict[str, Any]):
    """Notify direct ticket participants about an event they are allowed to see.

    Participants are the requester/beneficiary user plus all current assignees.
    Private events must pass ``visible_to_requester=False`` so requester-side
    recipients do not learn about staff-only activity.
    """
    ticket_id = payload.get("ticket_id")
    actor_user_id = payload.get("actor_user_id")
    event_type = payload.get("type") or "ticket_updated"
    title = payload.get("title")
    body = payload.get("body")
    visible_to_requester = payload.get("visible_to_requester", True)
    include_assignees = payload.get("include_assignees", True)

    with get_db() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            return

        recipients = _participant_recipient_ids(
            db,
            ticket,
            include_requester=bool(visible_to_requester),
            include_assignees=bool(include_assignees),
        )
        recipients.discard(actor_user_id)

        for uid in recipients:
            _create_in_app_notification(
                db,
                user_id=uid,
                type=event_type,
                title=title or f"Ticket {ticket.ticket_code} updated",
                body=body or "A ticket you are involved in was updated.",
                ticket_id=ticket.id,
            )
        db.commit()


@register_task("notify_beneficiary")
def notify_beneficiary(payload: Dict[str, Any]):
    """Backward-compatible alias for status-change participant notifications."""
    ticket_id = payload.get("ticket_id")
    with get_db() as db:
        ticket = db.get(Ticket, ticket_id)
        status = ticket.status if ticket else "updated"
    notify_ticket_event({
        **payload,
        "type": payload.get("type") or "status_changed",
        "title": payload.get("title") or (f"Ticket updated · {status.replace('_', ' ')}" if ticket_id else None),
        "body": payload.get("body") or f"Status changed to {status}.",
        "visible_to_requester": payload.get("visible_to_requester", True),
    })


@register_task("notify_comment")
def notify_comment(payload: Dict[str, Any]):
    """Notify ticket participants about a new comment.

    Public comments reach the requester + assignee + sector members.
    Private comments stay inside staff (sector members + assignee).
    The author is excluded.
    """
    ticket_id     = payload.get("ticket_id")
    actor_user_id = payload.get("actor_user_id")
    visibility    = payload.get("visibility", "public")
    notification_type = payload.get("type") or "comment_created"
    title = payload.get("title")
    body = payload.get("body")

    with get_db() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            return

        recipients = _participant_recipient_ids(
            db,
            ticket,
            include_requester=visibility == "public",
            include_assignees=True,
        )
        recipients.discard(actor_user_id)

        for uid in recipients:
            _create_in_app_notification(
                db,
                user_id=uid,
                type=notification_type,
                title=title or f"New comment on {ticket.ticket_code}",
                body=body or f"A {visibility} comment was posted.",
                ticket_id=ticket.id,
            )
        db.commit()


@register_task("notify_mentions")
def notify_mentions(payload: Dict[str, Any]):
    """Notify users `@mentioned` in a comment body.

    The producer hands us the lowercase usernames; here we resolve them
    to user_ids, drop any that can't see the comment (private comments
    only reach `can_see_private_comments` users), and emit one in-app
    notification per recipient. The actor is always excluded.

    Failure modes (non-existent username, non-staff target on a private
    comment) are silent — no error feedback in the comment UI yet, just
    the missing notification. Worth adding a "mentions resolved: X / Y"
    surface later.
    """
    from src.iam import rbac as _rbac
    from src.iam.principal import (
        Principal as _Principal,
        SectorMembership as _SectorMembership,
        ROLE_INTERNAL_USER as _ROLE_INTERNAL_USER,
    )

    ticket_id     = payload.get("ticket_id")
    comment_id    = payload.get("comment_id")
    actor_user_id = payload.get("actor_user_id")
    visibility    = payload.get("visibility", "public")
    usernames     = [u.lower() for u in payload.get("usernames", []) if u]
    if not usernames:
        return

    with get_db() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            return

        # Resolve usernames → users. We cap at the first 25 mentions
        # to defend against runaway or copy-pasted user lists.
        resolved = list(db.scalars(
            select(IAMUser).where(
                IAMUser.username.in_(usernames[:25]),
                IAMUser.is_active.is_(True),
            )
        ))

        # Hydrate the ticket's current_sector_code so RBAC predicates
        # below can answer correctly.
        sector_code = None
        if ticket.current_sector_id:
            from src.ticketing.models import Sector
            sector_code = db.scalar(
                select(Sector.code).where(Sector.id == ticket.current_sector_id)
            )
        setattr(ticket, "current_sector_code", sector_code)
        setattr(ticket, "sector_codes", [sector_code] if sector_code else [])
        setattr(ticket, "assignee_user_ids",
                list(_assignee_user_ids(db, ticket)))
        # Beneficiary -> user_id hydration for can_view_ticket.
        setattr(ticket, "beneficiary_user_id",
                db.scalar(select(Beneficiary.user_id).where(Beneficiary.id == ticket.beneficiary_id))
                if ticket.beneficiary_id else None)

        for u in resolved:
            if u.id == actor_user_id:
                continue  # don't ping yourself
            # Build a minimal Principal so `rbac.can_see_private_comments`
            # answers correctly. We pull membership data lazily — for
            # most users the visibility check terminates on the role
            # path before we need sectors.
            memberships = tuple(
                _SectorMembership(sector_code=sc, role=role)
                for (sc, role) in db.execute(
                    select(Sector.code, SectorMembership.membership_role)
                    .join(Sector, Sector.id == SectorMembership.sector_id)
                    .where(
                        SectorMembership.user_id == u.id,
                        SectorMembership.is_active.is_(True),
                    )
                ).all()
            )
            ghost = _Principal(
                user_id=u.id, keycloak_subject=u.keycloak_subject or "",
                username=u.username, email=u.email,
                user_type=u.user_type, global_roles=frozenset({_ROLE_INTERNAL_USER}),
                sector_memberships=memberships,
            )

            # Visibility floor: the mention recipient must at minimum be
            # able to view the ticket. Private mentions need
            # `can_see_private_comments`.
            if not _rbac.can_view_ticket(ghost, ticket):
                continue
            if visibility == "private" and not _rbac.can_see_private_comments(ghost, ticket):
                continue

            _create_in_app_notification(
                db,
                user_id=u.id,
                type="mention",
                title=f"You were mentioned on {ticket.ticket_code}",
                body=f"@{u.username} — see the {visibility} comment.",
                ticket_id=ticket.id,
            )
        db.commit()


@register_task("notify_unassigned")
def notify_unassigned(payload: Dict[str, Any]):
    """Notify the previously-assigned user (if not the actor) plus the sector
    chief that the ticket is back in the queue."""
    ticket_id     = payload.get("ticket_id")
    prev_user_id  = payload.get("previous_user_id")
    actor_user_id = payload.get("actor_user_id")
    with get_db() as db:
        ticket = db.get(Ticket, ticket_id)
        if not ticket:
            return

        recipients: set[str] = set()
        if prev_user_id and prev_user_id != actor_user_id:
            recipients.add(prev_user_id)
        if ticket.current_sector_id:
            members = db.scalars(
                select(SectorMembership.user_id)
                .where(SectorMembership.sector_id == ticket.current_sector_id, SectorMembership.is_active.is_(True))
            ).all()
            recipients.update(members)
        recipients.discard(actor_user_id)

        for uid in recipients:
            _create_in_app_notification(
                db,
                user_id=uid,
                type="ticket_unassigned",
                title=f"Ticket {ticket.ticket_code} unassigned",
                body="Back in the sector queue — open to claim.",
                ticket_id=ticket.id,
            )
        db.commit()

@register_task("send_email_notification")
def send_email_notification(payload: Dict[str, Any]):
    """Send an email notification if SMTP is configured."""
    if not Config.SMTP_HOST:
        logger.debug("skipping email: SMTP_HOST not configured")
        return
        
    recipient = payload.get("to")
    subject = payload.get("subject")
    body = payload.get("body")
    
    logger.info("sending email notification", extra={"to": recipient, "subject": subject})
    # Actual SMTP logic would go here
    # In Phase 5, we focus on in-app, but stub is ready for .env activation

def _create_in_app_notification(
    db: Session,
    user_id: str,
    type: str,
    title: str,
    body: str,
    ticket_id: Optional[str] = None
) -> Notification:
    """Helper to create an in-app notification record."""
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        ticket_id=ticket_id,
        delivered_channels={"in_app": True}
    )
    db.add(notification)
    logger.info("notification created", extra={"user_id": user_id, "type": type, "ticket_id": ticket_id})

    # Capture fields now (server_default created_at not yet set) and publish after commit.
    _nid, _uid, _ntype, _ntitle, _nbody, _tid = (
        notification.id, user_id, type, title, body, ticket_id
    )
    enqueue_after_commit(lambda: _publish_to_sse_raw(_uid, _nid, _ntype, _ntitle, _nbody, _tid))

    return notification


def _participant_recipient_ids(
    db: Session,
    ticket: Ticket,
    *,
    include_requester: bool,
    include_assignees: bool,
    include_watchers: bool = True,
) -> set[str]:
    """Collect notification recipients for a ticket event.

    Watchers (Phase 7) are folded in by default — they opted in to
    follow the ticket and shouldn't have to be assigned to receive
    updates. Visibility is still enforced when the recipient eventually
    reads the comment, so this isn't a leak.
    """
    recipients: set[str] = set()
    if include_requester:
        recipients.update(_requester_user_ids(db, ticket))
    if include_assignees:
        recipients.update(_assignee_user_ids(db, ticket))
    if include_watchers:
        from src.ticketing.service.watcher_service import watcher_user_ids
        recipients.update(watcher_user_ids(db, ticket.id))
    return recipients


def _requester_user_ids(db: Session, ticket: Ticket) -> set[str]:
    user_ids: set[str] = set()
    if ticket.created_by_user_id:
        user_ids.add(ticket.created_by_user_id)
    if ticket.beneficiary_id:
        beneficiary_user_id = db.scalar(
            select(Beneficiary.user_id).where(Beneficiary.id == ticket.beneficiary_id)
        )
        if beneficiary_user_id:
            user_ids.add(beneficiary_user_id)
    return user_ids


def _assignee_user_ids(db: Session, ticket: Ticket) -> set[str]:
    user_ids = set(
        db.scalars(
            select(TicketAssignee.user_id).where(TicketAssignee.ticket_id == ticket.id)
        ).all()
    )
    if ticket.assignee_user_id:
        user_ids.add(ticket.assignee_user_id)
    return user_ids

def _publish_to_sse_raw(
    user_id: str,
    notification_id: str,
    type: str,
    title: str,
    body: str,
    ticket_id: Optional[str],
) -> None:
    """Publish a notification payload to Redis after the DB transaction commits."""
    try:
        from src.common.redis_client import get_redis
        redis = get_redis()
        if not redis:
            return
        data = {
            "id": notification_id,
            "type": type,
            "title": title,
            "body": body,
            "ticket_id": ticket_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        redis.publish(f"notifications:{user_id}", json_dumps(data))
    except Exception as e:
        logger.error("failed to publish to sse", extra={"error": str(e)})

def json_dumps(data):
    import json
    return json.dumps(data)
