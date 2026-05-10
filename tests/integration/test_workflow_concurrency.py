from __future__ import annotations

import gevent
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from src.common.errors import ConcurrencyConflictError
from src.iam.principal import SectorMembership
from src.ticketing.models import AuditEvent, Ticket, TicketAssignmentHistory
from src.ticketing.service import workflow_service

from .conftest import create_beneficiary, create_sector, create_ticket, create_user, principal_for


def test_assign_to_me_allows_exactly_one_winner(db_session: Session, db_session_factory: sessionmaker[Session]):
    beneficiary_user = create_user(db_session, "beneficiary")
    sector = create_sector(db_session, "s10")
    beneficiary = create_beneficiary(db_session, beneficiary_user)
    ticket = create_ticket(
        db_session,
        beneficiary,
        created_by=beneficiary_user,
        current_sector=sector,
        status="assigned_to_sector",
    )

    principals = []
    for i in range(50):
        user = create_user(db_session, f"member-{i}")
        principals.append(principal_for(user, sectors=(SectorMembership("s10", "member"),)))
    db_session.commit()

    def attempt_assign(principal):
        session = db_session_factory()
        try:
            assigned = workflow_service.assign_to_me(session, principal, ticket.id)
            session.commit()
            return ("winner", assigned.assignee_user_id)
        except ConcurrencyConflictError:
            session.rollback()
            return ("conflict", principal.user_id)
        finally:
            session.close()

    jobs = [gevent.spawn(attempt_assign, principal) for principal in principals]
    gevent.joinall(jobs, timeout=20, raise_error=True)
    results = [job.value for job in jobs]

    winners = [user_id for status, user_id in results if status == "winner"]
    conflicts = [user_id for status, user_id in results if status == "conflict"]
    assert len(winners) == 1
    assert len(conflicts) == 49

    db_session.expire_all()
    saved = db_session.get(Ticket, ticket.id)
    assert saved.status == "in_progress"
    assert saved.assignee_user_id == winners[0]
    assert saved.last_active_assignee_user_id == winners[0]

    assignment_count = db_session.scalar(
        select(func.count()).select_from(TicketAssignmentHistory).where(TicketAssignmentHistory.ticket_id == ticket.id)
    )
    audit_count = db_session.scalar(
        select(func.count()).select_from(AuditEvent).where(AuditEvent.ticket_id == ticket.id)
    )
    assert assignment_count == 1
    assert audit_count == 1
