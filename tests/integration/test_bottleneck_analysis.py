from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.iam.principal import ROLE_ADMIN
from src.ticketing.models import TicketStatusHistory
from src.ticketing.service import monitor_service

from .conftest import create_beneficiary, create_sector, create_ticket, create_user, principal_for


def test_bottleneck_analysis(db_session: Session):
    admin_user = create_user(db_session, "bottleneck-admin")
    requester = create_user(db_session, "bottleneck-requester")
    sector = create_sector(db_session, "bottleneck-sector")
    beneficiary = create_beneficiary(db_session, requester)
    admin = principal_for(admin_user, roles={ROLE_ADMIN})

    now = datetime.now(timezone.utc)

    # Create a ticket that went through transitions and was closed
    t = create_ticket(db_session, beneficiary, created_by=requester, current_sector=sector, status="closed")
    t.created_at = now - timedelta(hours=10)
    t.closed_at = now
    
    # Transition 1: pending -> in_progress at now - 8h (Spent 2h in pending)
    h1 = TicketStatusHistory(ticket_id=t.id, old_status="pending", new_status="in_progress", created_at=now - timedelta(hours=8))
    # Transition 2: in_progress -> done at now - 2h (Spent 6h in in_progress)
    h2 = TicketStatusHistory(ticket_id=t.id, old_status="in_progress", new_status="done", created_at=now - timedelta(hours=2))
    # Transition 3: done -> closed at now (Spent 2h in done)
    h3 = TicketStatusHistory(ticket_id=t.id, old_status="done", new_status="closed", created_at=now)
    
    db_session.add_all([h1, h2, h3])
    db_session.flush()

    analysis = monitor_service._bottleneck_analysis(db_session, days=1)
    
    # Sort by status to check values
    analysis_map = {item["status"]: item for item in analysis}
    
    assert analysis_map["pending"]["avg_minutes"] == 120.0
    assert analysis_map["in_progress"]["avg_minutes"] == 360.0
    assert analysis_map["done"]["avg_minutes"] == 120.0
