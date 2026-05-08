from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.ticketing import notifications
from src.ticketing.models import Notification, TicketAssignee

from .conftest import create_beneficiary, create_sector, create_ticket, create_user


@contextmanager
def _same_session(db: Session):
    yield db


def _notification_context(db: Session):
    requester = create_user(db, "notify-requester")
    primary = create_user(db, "notify-primary")
    secondary = create_user(db, "notify-secondary")
    actor = create_user(db, "notify-actor")
    sector = create_sector(db, "notif")
    beneficiary = create_beneficiary(db, requester)
    ticket = create_ticket(
        db,
        beneficiary,
        created_by=requester,
        current_sector=sector,
        status="in_progress",
        assignee=primary,
    )
    db.add(TicketAssignee(ticket_id=ticket.id, user_id=secondary.id, is_primary=False))
    db.flush()
    return ticket, requester, primary, secondary, actor


def _notification_user_ids(db: Session) -> set[str]:
    return set(db.scalars(select(Notification.user_id)).all())


def test_ticket_event_notifies_requester_and_all_assignees(monkeypatch, db_session: Session):
    ticket, requester, primary, secondary, actor = _notification_context(db_session)
    monkeypatch.setattr(notifications, "get_db", lambda: _same_session(db_session))
    monkeypatch.setattr(notifications, "_publish_to_sse", lambda *_args, **_kwargs: None)

    notifications.notify_ticket_event({
        "ticket_id": ticket.id,
        "actor_user_id": actor.id,
        "type": "status_changed",
        "title": "Ticket updated",
        "body": "Status changed.",
    })

    assert _notification_user_ids(db_session) == {requester.id, primary.id, secondary.id}


def test_public_comment_notifies_requester_and_assignees_except_author(monkeypatch, db_session: Session):
    ticket, requester, primary, secondary, _actor = _notification_context(db_session)
    monkeypatch.setattr(notifications, "get_db", lambda: _same_session(db_session))
    monkeypatch.setattr(notifications, "_publish_to_sse", lambda *_args, **_kwargs: None)

    notifications.notify_comment({
        "ticket_id": ticket.id,
        "actor_user_id": primary.id,
        "visibility": "public",
    })

    assert _notification_user_ids(db_session) == {requester.id, secondary.id}


def test_private_comment_does_not_notify_requester(monkeypatch, db_session: Session):
    ticket, requester, primary, secondary, _actor = _notification_context(db_session)
    monkeypatch.setattr(notifications, "get_db", lambda: _same_session(db_session))
    monkeypatch.setattr(notifications, "_publish_to_sse", lambda *_args, **_kwargs: None)

    notifications.notify_comment({
        "ticket_id": ticket.id,
        "actor_user_id": primary.id,
        "visibility": "private",
    })

    assert requester.id not in _notification_user_ids(db_session)
    assert _notification_user_ids(db_session) == {secondary.id}
