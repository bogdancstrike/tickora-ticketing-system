"""pytest-bdd step definitions for `features/comments_and_review.feature`.

Acceptance-style coverage of the new self-assignment policy and the
distributor review-and-route happy path. Mirrors the structure of
`test_workflow_acceptance.py`.
"""
from __future__ import annotations

import pytest
from pytest_bdd import given, scenarios, then, when
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.common.errors import PermissionDeniedError
from src.iam.principal import (
    SectorMembership,
    ROLE_ADMIN,
    ROLE_DISTRIBUTOR,
    ROLE_INTERNAL_USER,
)
from src.audit import events
from src.ticketing.models import AuditEvent, TicketComment, TicketSectorHistory
from src.ticketing.service import comment_service, review_service

from .conftest import (
    create_beneficiary,
    create_sector,
    create_ticket,
    create_user,
    principal_for,
)

scenarios("features/comments_and_review.feature")


# ── Givens ──────────────────────────────────────────────────────────────────

@given("an in-progress ticket assigned to a sector member", target_fixture="ctx")
def _in_progress_assigned(db_session: Session):
    sector = create_sector(db_session, "s10")
    beneficiary_user = create_user(db_session, "beneficiary")
    member_user = create_user(db_session, "member")
    beneficiary = create_beneficiary(db_session, beneficiary_user)
    ticket = create_ticket(
        db_session, beneficiary,
        created_by=beneficiary_user, current_sector=sector,
        status="in_progress", assignee=member_user, last_active_assignee=member_user,
    )
    db_session.commit()
    return {
        "ticket_id": ticket.id,
        "assignee": principal_for(
            member_user, roles={ROLE_INTERNAL_USER},
            sectors=(SectorMembership("s10", "member"),),
        ),
        "beneficiary": principal_for(beneficiary_user, roles={ROLE_INTERNAL_USER}),
    }


@given("an in-progress ticket assigned to another sector member", target_fixture="ctx")
def _in_progress_other_member(db_session: Session):
    sector = create_sector(db_session, "s10")
    beneficiary_user = create_user(db_session, "beneficiary")
    member_user = create_user(db_session, "member.s10")
    chief_user = create_user(db_session, "chief.s10")
    beneficiary = create_beneficiary(db_session, beneficiary_user)
    ticket = create_ticket(
        db_session, beneficiary,
        created_by=beneficiary_user, current_sector=sector,
        status="in_progress", assignee=member_user, last_active_assignee=member_user,
    )
    db_session.commit()
    return {
        "ticket_id": ticket.id,
        "chief": principal_for(
            chief_user, roles={ROLE_INTERNAL_USER},
            sectors=(SectorMembership("s10", "chief"),),
        ),
    }


@given("a pending ticket awaiting distribution", target_fixture="ctx")
def _pending_ticket(db_session: Session):
    create_sector(db_session, "s10")
    distributor_user = create_user(db_session, "distributor")
    beneficiary_user = create_user(db_session, "beneficiary")
    beneficiary = create_beneficiary(db_session, beneficiary_user)
    ticket = create_ticket(
        db_session, beneficiary, created_by=beneficiary_user, status="pending",
    )
    db_session.commit()
    return {
        "ticket_id": ticket.id,
        "distributor": principal_for(distributor_user, roles={ROLE_DISTRIBUTOR}),
    }


@given("an in-progress ticket with one public and one private comment", target_fixture="ctx")
def _ticket_with_mixed_comments(db_session: Session):
    sector = create_sector(db_session, "s10")
    beneficiary_user = create_user(db_session, "beneficiary")
    member_user = create_user(db_session, "member")
    beneficiary = create_beneficiary(db_session, beneficiary_user)
    ticket = create_ticket(
        db_session, beneficiary,
        created_by=beneficiary_user, current_sector=sector,
        status="in_progress", assignee=member_user, last_active_assignee=member_user,
    )
    db_session.commit()
    assignee = principal_for(
        member_user, roles={ROLE_INTERNAL_USER},
        sectors=(SectorMembership("s10", "member"),),
    )
    comment_service.create(
        db_session, assignee, ticket.id, body="public progress", visibility="public",
    )
    comment_service.create(
        db_session, assignee, ticket.id, body="private internal", visibility="private",
    )
    db_session.commit()
    return {
        "ticket_id": ticket.id,
        "beneficiary": principal_for(beneficiary_user, roles={ROLE_INTERNAL_USER}),
    }


# ── Whens ───────────────────────────────────────────────────────────────────

@when('the assignee posts a public comment "Working on it"')
def _post_public(db_session: Session, ctx):
    ctx["comment"] = comment_service.create(
        db_session, ctx["assignee"], ctx["ticket_id"],
        body="Working on it", visibility="public",
    )


@when("the chief tries to post a public comment")
def _chief_blocked(db_session: Session, ctx):
    try:
        comment_service.create(
            db_session, ctx["chief"], ctx["ticket_id"],
            body="butting in", visibility="public",
        )
        ctx["error"] = None
    except PermissionDeniedError as e:
        ctx["error"] = e


@when("a distributor reviews the ticket and routes it to sector s10")
def _route(db_session: Session, ctx):
    review_service.review(
        db_session, ctx["distributor"], ctx["ticket_id"],
        {"sector_code": "s10", "category": "general"},
    )


@when("the beneficiary lists the comments")
def _list_for_beneficiary(db_session: Session, ctx):
    ctx["listed"] = comment_service.list_(
        db_session, ctx["beneficiary"], ctx["ticket_id"],
    )


# ── Thens ──────────────────────────────────────────────────────────────────

@then("the comment is stored with public visibility and a comment_created audit entry")
def _public_persisted(db_session: Session, ctx):
    c = ctx["comment"]
    assert c.visibility == "public"
    audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == events.COMMENT_CREATED,
            AuditEvent.ticket_id == ctx["ticket_id"],
        )
    ).all()
    assert len(audit) >= 1


@then("the comment is rejected with a permission_denied error")
def _rejected(ctx):
    assert isinstance(ctx["error"], PermissionDeniedError)


@then("an access_denied audit entry exists")
def _access_denied_audit(db_session: Session, ctx):
    audit = db_session.scalars(
        select(AuditEvent).where(
            AuditEvent.action == events.ACCESS_DENIED,
            AuditEvent.ticket_id == ctx["ticket_id"],
        )
    ).all()
    assert len(audit) >= 1


@then("the ticket is assigned to sector s10 with assigned_to_sector status")
def _routed(db_session: Session, ctx):
    from src.ticketing.models import Sector, Ticket
    t = db_session.get(Ticket, ctx["ticket_id"])
    s = db_session.get(Sector, t.current_sector_id)
    assert s.code == "s10"
    assert t.status == "assigned_to_sector"


@then("a sector-history entry exists for the routing")
def _sector_history(db_session: Session, ctx):
    rows = db_session.scalars(
        select(TicketSectorHistory).where(TicketSectorHistory.ticket_id == ctx["ticket_id"])
    ).all()
    assert len(rows) >= 1


@then("only the public comment is returned")
def _only_public(ctx):
    visibilities = {c.visibility for c in ctx["listed"]}
    assert visibilities == {"public"}
    assert len(ctx["listed"]) == 1
