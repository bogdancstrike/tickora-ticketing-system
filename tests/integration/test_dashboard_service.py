from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.iam.principal import ROLE_ADMIN, SectorMembership
from src.ticketing.service import monitor_service

from .conftest import create_beneficiary, create_sector, create_ticket, create_user, principal_for


def test_global_kpis_use_live_ticket_data(db_session: Session):
    admin_user = create_user(db_session, "dash-admin")
    requester = create_user(db_session, "dash-requester")
    sector = create_sector(db_session, "dash1")
    beneficiary = create_beneficiary(db_session, requester)
    admin = principal_for(admin_user, roles={ROLE_ADMIN})

    created = create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        current_sector=sector,
        status="pending",
    )
    created.created_at = datetime.now(timezone.utc)
    db_session.flush()

    before = dashboard_service.global_(db_session, admin)["kpis"]
    assert before["total_tickets"] == 1
    assert before["active_tickets"] == 1
    assert before["new_today"] == 1
    assert before["closed_today"] == 0

    closed = create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        current_sector=sector,
        status="closed",
    )
    closed.created_at = datetime.now(timezone.utc) - timedelta(days=2)
    closed.closed_at = datetime.now(timezone.utc)
    closed.done_at = closed.closed_at - timedelta(hours=1)
    closed_without_closed_at = create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        current_sector=sector,
        status="closed",
    )
    closed_without_closed_at.created_at = datetime.now(timezone.utc) - timedelta(days=2)
    closed_without_closed_at.closed_at = None
    closed_without_closed_at.updated_at = datetime.now(timezone.utc)
    db_session.flush()

    after = dashboard_service.global_(db_session, admin)["kpis"]
    assert after["total_tickets"] == 3
    assert after["active_tickets"] == 1
    assert after["new_today"] == 1
    assert after["closed_today"] == 2
    assert after["avg_resolution_minutes"] is not None

    today = datetime.now(timezone.utc).date().isoformat()
    today_point = next(p for p in dashboard_service.timeseries(db_session, admin) if p["date"] == today)
    assert today_point["closed"] == 2


def test_sector_kpis_use_live_ticket_data(db_session: Session):
    requester = create_user(db_session, "sector-requester")
    member = create_user(db_session, "sector-member")
    sector = create_sector(db_session, "dash2")
    beneficiary = create_beneficiary(db_session, requester)
    principal = principal_for(member, sectors=(SectorMembership(sector.code, "member"),))

    unassigned = create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        current_sector=sector,
        status="assigned_to_sector",
    )
    unassigned.sla_status = "breached"

    create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        current_sector=sector,
        status="in_progress",
        assignee=member,
    )

    done = create_ticket(
        db_session,
        beneficiary,
        created_by=requester,
        current_sector=sector,
        status="done",
        assignee=member,
    )
    done.done_at = datetime.now(timezone.utc)
    done.created_at = done.done_at - timedelta(hours=2)
    done.reopened_count = 1
    db_session.flush()

    kpis = dashboard_service.sector(db_session, principal, sector.code)["kpis"]
    assert kpis["active"] == 2
    assert kpis["unassigned"] == 1
    assert kpis["done"] == 1
    assert kpis["sla_breached"] == 1
    assert kpis["reopened"] == 1
    assert kpis["avg_resolution_minutes"] == 120.0
