from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.iam.principal import ROLE_ADMIN
from src.ticketing.models import TicketComment
from src.ticketing.service import monitor_service

from .conftest import create_beneficiary, create_sector, create_ticket, create_user, principal_for


def test_stale_tickets_metrics(db_session: Session):
    admin_user = create_user(db_session, "stale-admin")
    requester = create_user(db_session, "stale-requester")
    sector = create_sector(db_session, "stale-sector")
    beneficiary = create_beneficiary(db_session, requester)
    admin = principal_for(admin_user, roles={ROLE_ADMIN})

    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(hours=24)

    # 1. NOT stale: created recently, no comments
    t1 = create_ticket(db_session, beneficiary, created_by=requester, current_sector=sector, status="pending")
    t1.created_at = now - timedelta(hours=5)
    
    # 2. IS stale: created long ago, no comments
    t2 = create_ticket(db_session, beneficiary, created_by=requester, current_sector=sector, status="pending")
    t2.created_at = now - timedelta(hours=48)
    
    # 3. NOT stale: created long ago, but has recent comment
    t3 = create_ticket(db_session, beneficiary, created_by=requester, current_sector=sector, status="in_progress")
    t3.created_at = now - timedelta(hours=48)
    c3 = TicketComment(ticket_id=t3.id, author_user_id=admin_user.id, visibility="public", body="recent", created_at=now - timedelta(hours=1))
    db_session.add(c3)
    
    # 4. IS stale: created long ago, last comment is also old
    t4 = create_ticket(db_session, beneficiary, created_by=requester, current_sector=sector, status="in_progress")
    t4.created_at = now - timedelta(hours=72)
    c4 = TicketComment(ticket_id=t4.id, author_user_id=admin_user.id, visibility="private", body="old", created_at=now - timedelta(hours=48))
    db_session.add(c4)
    
    # 5. NOT stale: done, even if old
    t5 = create_ticket(db_session, beneficiary, created_by=requester, current_sector=sector, status="done")
    t5.created_at = now - timedelta(hours=48)
    
    db_session.flush()

    # We expect t2 and t4 to be stale
    stale = monitor_service._stale_tickets(db_session, admin, hours=24)
    assert len(stale) == 2
    codes = {s["ticket_code"] for s in stale}
    assert t2.ticket_code in codes
    assert t4.ticket_code in codes


def test_monitor_overview_includes_stale_tickets(db_session: Session):
    admin_user = create_user(db_session, "overview-admin")
    admin = principal_for(admin_user, roles={ROLE_ADMIN})
    
    # Create one stale ticket
    requester = create_user(db_session, "overview-req")
    sector = create_sector(db_session, "overview-sec")
    beneficiary = create_beneficiary(db_session, requester)
    t = create_ticket(db_session, beneficiary, created_by=requester, current_sector=sector, status="pending")
    t.created_at = datetime.now(timezone.utc) - timedelta(hours=48)
    db_session.flush()
    
    overview = monitor_service.monitor_overview(db_session, admin)
    assert "stale_tickets" in overview
    assert len(overview["stale_tickets"]) == 1
    assert overview["stale_tickets"][0]["ticket_code"] == t.ticket_code
