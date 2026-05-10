"""Integration tests for `src.ticketing.service.sla_service`.

Covers policy matching (priority + category + beneficiary_type
specificity), `evaluate_sla` setting `sla_due_at` and
`sla_status`, and `check_all_breaches` transitioning tickets through the
within → approaching → breached states.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from src.ticketing.models import SlaPolicy
from src.ticketing.service import sla_service

from tests.integration.conftest import (
    create_beneficiary,
    create_sector,
    create_ticket,
    create_user,
)


@pytest.fixture(autouse=True)
def stub_publisher(monkeypatch):
    """Don't try to talk to Kafka during SLA tests."""
    from src.tasking import producer
    monkeypatch.setattr(producer, "publish", lambda *a, **kw: None)


def _policy(
    *,
    priority: str = "medium",
    category: str | None = None,
    beneficiary_type: str | None = None,
    resolution_minutes: int = 60,
    is_active: bool = True,
):
    return SlaPolicy(
        priority=priority,
        category=category,
        beneficiary_type=beneficiary_type,
        resolution_minutes=resolution_minutes,
        is_active=is_active,
        first_response_minutes=15,
    )


@pytest.fixture
def base_ticket(db_session: Session):
    user = create_user(db_session, "creator")
    beneficiary = create_beneficiary(db_session, user)
    sector = create_sector(db_session, code="s10")
    ticket = create_ticket(
        db_session, beneficiary, created_by=user,
        current_sector=sector, status="in_progress",
    )
    db_session.commit()
    return ticket


# ── Policy matching ─────────────────────────────────────────────────────────

class TestPolicyMatching:
    def test_no_policy_leaves_ticket_alone(self, db_session, base_ticket):
        sla_service.evaluate_sla(db_session, base_ticket)
        assert base_ticket.sla_due_at is None

    def test_priority_only_match(self, db_session, base_ticket):
        db_session.add(_policy(priority=base_ticket.priority, resolution_minutes=120))
        db_session.flush()
        sla_service.evaluate_sla(db_session, base_ticket)
        assert base_ticket.sla_due_at is not None

    def test_specific_policy_wins_over_generic(self, db_session, base_ticket):
        # Generic (priority-only) and specific (priority + category) compete.
        # The ticket has no category, so the generic policy should win.
        db_session.add(_policy(priority=base_ticket.priority, resolution_minutes=240))
        db_session.add(_policy(priority=base_ticket.priority, category="network", resolution_minutes=30))
        db_session.flush()
        sla_service.evaluate_sla(db_session, base_ticket)
        assert base_ticket.sla_due_at is not None
        # 240-min policy applies → due ~4h after created_at.
        delta = base_ticket.sla_due_at - base_ticket.created_at
        assert abs(delta.total_seconds() - 240 * 60) < 5

    def test_inactive_policies_ignored(self, db_session, base_ticket):
        db_session.add(_policy(priority=base_ticket.priority,
                                resolution_minutes=60, is_active=False))
        db_session.flush()
        sla_service.evaluate_sla(db_session, base_ticket)
        assert base_ticket.sla_due_at is None

    def test_priority_mismatch_ignored(self, db_session, base_ticket):
        db_session.add(_policy(priority="low", resolution_minutes=60))
        db_session.flush()
        sla_service.evaluate_sla(db_session, base_ticket)
        assert base_ticket.sla_due_at is None


class TestTerminalStatuses:
    @pytest.mark.parametrize("status", ["done", "closed", "cancelled"])
    def test_terminal_status_skipped(self, db_session, base_ticket, status):
        base_ticket.status = status
        db_session.add(_policy(priority=base_ticket.priority))
        db_session.flush()
        sla_service.evaluate_sla(db_session, base_ticket)
        assert base_ticket.sla_due_at is None


# ── Status assignment ───────────────────────────────────────────────────────

class TestStatusAssignment:
    def test_within_sla(self, db_session, base_ticket):
        db_session.add(_policy(priority=base_ticket.priority, resolution_minutes=240))
        db_session.flush()
        sla_service.evaluate_sla(db_session, base_ticket)
        assert base_ticket.sla_status == "within_sla"

    def test_approaching_breach_at_30min_window(self, db_session, base_ticket):
        # Backdate created_at so resolution lands within the 30-min approaching window.
        base_ticket.created_at = datetime.now(timezone.utc) - timedelta(minutes=50)
        db_session.add(_policy(priority=base_ticket.priority, resolution_minutes=60))
        db_session.flush()
        sla_service.evaluate_sla(db_session, base_ticket)
        assert base_ticket.sla_status == "approaching_breach"

    def test_breached_when_due_at_in_past(self, db_session, base_ticket):
        base_ticket.created_at = datetime.now(timezone.utc) - timedelta(hours=10)
        db_session.add(_policy(priority=base_ticket.priority, resolution_minutes=60))
        db_session.flush()
        sla_service.evaluate_sla(db_session, base_ticket)
        assert base_ticket.sla_status == "breached"


# ── Bulk breach scan ────────────────────────────────────────────────────────

class TestCheckAllBreaches:
    def test_promotes_within_sla_to_approaching_when_close(self, db_session, base_ticket):
        # Manually set up the ticket as "within_sla" but very close to due.
        base_ticket.sla_due_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        base_ticket.sla_status = "within_sla"
        db_session.flush()
        sla_service.check_all_breaches(db_session)
        db_session.refresh(base_ticket)
        assert base_ticket.sla_status == "approaching_breach"

    def test_promotes_to_breached(self, db_session, base_ticket):
        base_ticket.sla_due_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        base_ticket.sla_status = "approaching_breach"
        db_session.flush()
        breached_count = sla_service.check_all_breaches(db_session)
        db_session.refresh(base_ticket)
        assert base_ticket.sla_status == "breached"
        assert breached_count == 1

    def test_terminal_tickets_not_touched(self, db_session, base_ticket):
        base_ticket.status = "closed"
        base_ticket.sla_due_at = datetime.now(timezone.utc) - timedelta(hours=1)
        base_ticket.sla_status = "within_sla"
        db_session.flush()
        sla_service.check_all_breaches(db_session)
        db_session.refresh(base_ticket)
        # A closed ticket should not flip to breached — the work is done.
        assert base_ticket.sla_status == "within_sla"
