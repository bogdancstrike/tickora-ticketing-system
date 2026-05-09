from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.iam.principal import ROLE_ADMIN, ROLE_DISTRIBUTOR, SectorMembership
from src.ticketing.service import monitor_service
from src.ticketing.models import TicketStatusHistory

from .conftest import create_beneficiary, create_sector, create_ticket, create_user, principal_for


def test_closed_today_counts_done_and_closed_tickets(db_session: Session):
    admin_user = create_user(db_session, "refine-admin")
    requester = create_user(db_session, "refine-requester")
    sector = create_sector(db_session, "refine1")
    beneficiary = create_beneficiary(db_session, requester)
    admin = principal_for(admin_user, roles={ROLE_ADMIN})

    # 1. Done today
    done_today = create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        current_sector=sector,
        status="done",
    )
    done_today.done_at = datetime.now(timezone.utc)
    
    # 2. Closed today
    closed_today = create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        current_sector=sector,
        status="closed",
    )
    closed_today.closed_at = datetime.now(timezone.utc)
    
    # 3. Pending (active)
    create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        current_sector=sector,
        status="pending",
    )
    
    db_session.flush()

    kpis = monitor_service.monitor_global(db_session, admin)["kpis"]
    
    # CURRENT BEHAVIOR: closed_today uses _closed_timestamp which currently is:
    # func.coalesce(Ticket.closed_at, case((Ticket.status == "closed", Ticket.updated_at), else_=None))
    # It does NOT include "done" status unless closed_at is set.
    # In my test, done_today has done_at set but status is "done".
    
    assert kpis["closed_today"] == 2


def test_monitor_distributor_lists(db_session: Session):
    admin_user = create_user(db_session, "dist-admin")
    distributor_user = create_user(db_session, "dist-user")
    requester = create_user(db_session, "dist-requester")
    sector = create_sector(db_session, "dist1")
    beneficiary = create_beneficiary(db_session, requester)
    
    admin = principal_for(admin_user, roles={ROLE_ADMIN})
    distributor = principal_for(distributor_user, roles={ROLE_DISTRIBUTOR})

    # 1. Ticket in pending status (not reviewed)
    pending_ticket = create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        status="pending",
    )
    
    # 2. Ticket transitioned out of pending today
    reviewed_ticket = create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        status="assigned_to_sector",
        current_sector=sector,
    )
    # Add history entry for the review
    history = TicketStatusHistory(
        ticket_id=reviewed_ticket.id,
        old_status="pending",
        new_status="assigned_to_sector",
        changed_by_user_id=distributor_user.id,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1)
    )
    db_session.add(history)
    db_session.flush()

    dist_data = monitor_service.monitor_distributor(db_session, admin)
    
    assert "not_reviewed" in dist_data
    assert "reviewed_today" in dist_data
    
    assert any(t["id"] == pending_ticket.id for t in dist_data["not_reviewed"])
    assert any(t["id"] == reviewed_ticket.id for t in dist_data["reviewed_today"])
