from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from src.common.errors import BusinessRuleError, ConcurrencyConflictError
from src.iam.principal import ROLE_INTERNAL_USER, SectorMembership
from src.ticketing.service import workflow_service

from .conftest import create_beneficiary, create_sector, create_ticket, create_user, principal_for


def _sector_member_context(db_session: Session, *, status: str):
    sector = create_sector(db_session, "sec1")
    requester = create_user(db_session, f"requester-{status}")
    member = create_user(db_session, f"member-{status}")
    beneficiary = create_beneficiary(db_session, requester)
    ticket = create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        current_sector=sector,
        status=status,
        assignee=None,
        last_active_assignee=member,
    )
    principal = principal_for(
        member,
        roles={ROLE_INTERNAL_USER},
        sectors=(SectorMembership("sec1", "member"),),
    )
    db_session.commit()
    return ticket, principal


def test_assign_to_me_rejects_done_ticket(db_session: Session):
    ticket, principal = _sector_member_context(db_session, status="done")

    with pytest.raises(ConcurrencyConflictError):
        workflow_service.assign_to_me(db_session, principal, ticket.id)


def test_assign_to_me_rejects_cancelled_ticket(db_session: Session):
    ticket, principal = _sector_member_context(db_session, status="cancelled")

    with pytest.raises(ConcurrencyConflictError):
        workflow_service.assign_to_me(db_session, principal, ticket.id)


def test_change_status_rejects_pending_target(db_session: Session):
    ticket, principal = _sector_member_context(db_session, status="assigned_to_sector")
    workflow_service.assign_to_me(db_session, principal, ticket.id)

    with pytest.raises(BusinessRuleError, match="pending"):
        workflow_service.change_status(db_session, principal, ticket.id, "pending")


def test_change_status_requires_reason_to_reopen(db_session: Session):
    ticket, principal = _sector_member_context(db_session, status="done")
    ticket.assignee_user_id = principal.user_id
    db_session.flush()

    with pytest.raises(BusinessRuleError, match="reason"):
        workflow_service.change_status(db_session, principal, ticket.id, "in_progress")
