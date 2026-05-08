from __future__ import annotations

from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.iam.principal import SectorMembership
from src.ticketing import events
from src.ticketing.models import AuditEvent, TicketAssignmentHistory, TicketStatusHistory
from src.ticketing.service import workflow_service

from .conftest import (
    create_beneficiary,
    create_sector,
    create_ticket,
    create_user,
    principal_for,
)

scenarios("features/workflow.feature")


@given(parsers.parse("a pending ticket routed to sector {sector_code}"), target_fixture="ctx")
def pending_ticket(db_session: Session, sector_code: str):
    beneficiary_user = create_user(db_session, "beneficiary")
    member_user = create_user(db_session, "member")
    sector = create_sector(db_session, sector_code)
    beneficiary = create_beneficiary(db_session, beneficiary_user)
    ticket = create_ticket(
        db_session,
        beneficiary,
        created_by=beneficiary_user,
        current_sector=sector,
        status="assigned_to_sector",
    )
    db_session.commit()
    return {
        "ticket_id": ticket.id,
        "member": principal_for(member_user, sectors=(SectorMembership(sector_code, "member"),)),
        "beneficiary": principal_for(beneficiary_user),
    }


@given("an in-progress ticket assigned to a sector member", target_fixture="ctx")
def in_progress_ticket(db_session: Session):
    beneficiary_user = create_user(db_session, "beneficiary")
    member_user = create_user(db_session, "member")
    sector = create_sector(db_session, "s10")
    beneficiary = create_beneficiary(db_session, beneficiary_user)
    ticket = create_ticket(
        db_session,
        beneficiary,
        created_by=beneficiary_user,
        current_sector=sector,
        status="in_progress",
        assignee=member_user,
        last_active_assignee=member_user,
    )
    db_session.commit()
    return {
        "ticket_id": ticket.id,
        "member": principal_for(member_user, sectors=(SectorMembership("s10", "member"),)),
        "beneficiary": principal_for(beneficiary_user),
    }


@given("a closed ticket with a last active assignee", target_fixture="ctx")
def closed_ticket(db_session: Session):
    beneficiary_user = create_user(db_session, "beneficiary")
    member_user = create_user(db_session, "member")
    sector = create_sector(db_session, "s10")
    beneficiary = create_beneficiary(db_session, beneficiary_user)
    ticket = create_ticket(
        db_session,
        beneficiary,
        created_by=beneficiary_user,
        current_sector=sector,
        status="closed",
        last_active_assignee=member_user,
    )
    db_session.commit()
    return {
        "ticket_id": ticket.id,
        "member_user_id": member_user.id,
        "beneficiary": principal_for(beneficiary_user),
    }


@when("a sector member assigns the ticket to themselves")
def assign_to_self(db_session: Session, ctx):
    workflow_service.assign_to_me(db_session, ctx["member"], ctx["ticket_id"])
    db_session.commit()


@when("the assignee marks the ticket done with a resolution")
def mark_done(db_session: Session, ctx):
    workflow_service.mark_done(
        db_session,
        ctx["member"],
        ctx["ticket_id"],
        resolution="Restarted the upstream router and verified service recovery.",
    )
    db_session.commit()


@when("the beneficiary closes the ticket")
def close_ticket(db_session: Session, ctx):
    workflow_service.close(db_session, ctx["beneficiary"], ctx["ticket_id"])
    db_session.commit()


@when("the beneficiary reopens the ticket")
def reopen_ticket(db_session: Session, ctx):
    workflow_service.reopen(
        db_session,
        ctx["beneficiary"],
        ctx["ticket_id"],
        reason="The same issue reappeared.",
    )
    db_session.commit()


@then("the ticket is in progress and assigned to that member")
def assert_assigned(db_session: Session, ctx):
    ticket = workflow_service._load(db_session, ctx["ticket_id"])
    assert ticket.status == "in_progress"
    assert ticket.assignee_user_id == ctx["member"].user_id
    assert ticket.last_active_assignee_user_id == ctx["member"].user_id
    assert ticket.first_response_at is not None


@then("assignment status and audit entries are recorded")
def assert_assignment_history(db_session: Session, ctx):
    assignment = db_session.scalar(
        select(TicketAssignmentHistory).where(TicketAssignmentHistory.ticket_id == ctx["ticket_id"])
    )
    status = db_session.scalar(
        select(TicketStatusHistory).where(
            TicketStatusHistory.ticket_id == ctx["ticket_id"],
            TicketStatusHistory.new_status == "in_progress",
        )
    )
    audit = db_session.scalar(
        select(AuditEvent).where(
            AuditEvent.ticket_id == ctx["ticket_id"],
            AuditEvent.action == events.TICKET_ASSIGNED_TO_USER,
        )
    )
    assert assignment is not None
    assert status is not None
    assert audit is not None


@then("the ticket is closed with done and closed history entries")
def assert_closed(db_session: Session, ctx):
    ticket = workflow_service._load(db_session, ctx["ticket_id"])
    statuses = set(
        db_session.scalars(
            select(TicketStatusHistory.new_status).where(TicketStatusHistory.ticket_id == ctx["ticket_id"])
        )
    )
    assert ticket.status == "closed"
    assert {"done", "closed"}.issubset(statuses)


@then("the ticket is reopened for the last active assignee")
def assert_reopened(db_session: Session, ctx):
    ticket = workflow_service._load(db_session, ctx["ticket_id"])
    assert ticket.status == "reopened"
    assert ticket.assignee_user_id == ctx["member_user_id"]
    assert ticket.reopened_count == 1
