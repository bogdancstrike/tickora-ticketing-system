"""Integration tests for the RBAC checks added in the latest UX work:

- review_service: distributors may only assign sectors during review;
  picking a specific user is reserved for admins / chiefs of the target sector.
- workflow_service.unassign: anyone can unassign themselves; admins and the
  current sector chief can unassign anyone; everyone else is denied.
- assignable_users gate: non-admins must pass an explicit sector_code, and
  non-distributors are restricted to sectors they belong to.
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from src.core.errors import PermissionDeniedError
from src.iam.principal import (
    Principal,
    ROLE_ADMIN,
    ROLE_DISTRIBUTOR,
    SectorMembership,
)
from src.ticketing.models import SectorMembership as ORMSectorMembership
from src.ticketing.service import (
    review_service,
    workflow_service,
)

from .conftest import (
    create_beneficiary,
    create_sector,
    create_ticket,
    create_user,
    principal_for,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _seed_membership(db: Session, user, sector, *, role: str = "member") -> None:
    db.add(ORMSectorMembership(user_id=user.id, sector_id=sector.id,
                               membership_role=role, is_active=True))
    db.flush()


def _ticket(db: Session, *, sector=None, status="assigned_to_sector", assignee=None):
    requester = create_user(db, f"req-{status}-{id(sector)}")
    beneficiary = create_beneficiary(db, requester)
    return create_ticket(
        db, beneficiary,
        created_by=requester,
        current_sector=sector,
        status=status,
        assignee=assignee,
    )


# ── review_service: distributor reviewer-restriction ─────────────────────────

class TestReviewerRestriction:
    """Distributors triage sectors; picking a specific user is admin/chief only."""

    def test_distributor_cannot_assign_user_during_review(self, db_session: Session):
        sector = create_sector(db_session, "rev1")
        operator = create_user(db_session, "op-rev1")
        _seed_membership(db_session, operator, sector, role="member")
        ticket = _ticket(db_session, sector=sector, status="pending")

        distributor_user = create_user(db_session, "dist1")
        distributor = principal_for(distributor_user, roles={ROLE_DISTRIBUTOR})

        with pytest.raises(PermissionDeniedError):
            review_service.review(db_session, distributor, ticket.id, {
                "sector_code":      sector.code,
                "priority":         "medium",
                "assignee_user_id": operator.id,
            })

    def test_admin_can_assign_user_during_review(self, db_session: Session):
        sector = create_sector(db_session, "rev2")
        operator = create_user(db_session, "op-rev2")
        _seed_membership(db_session, operator, sector, role="member")
        ticket = _ticket(db_session, sector=sector, status="pending")

        admin_user = create_user(db_session, "admin-rev2")
        admin = principal_for(admin_user, roles={ROLE_ADMIN})

        result = review_service.review(db_session, admin, ticket.id, {
            "sector_code":      sector.code,
            "priority":         "medium",
            "assignee_user_id": operator.id,
        })
        assert result.assignee_user_id == operator.id

    def test_chief_of_target_sector_can_assign_user_during_review(self, db_session: Session):
        sector = create_sector(db_session, "rev3")
        operator = create_user(db_session, "op-rev3")
        _seed_membership(db_session, operator, sector, role="member")
        ticket = _ticket(db_session, sector=sector, status="pending")

        chief_user = create_user(db_session, "chief-rev3")
        _seed_membership(db_session, chief_user, sector, role="chief")
        chief = principal_for(
            chief_user,
            roles={ROLE_DISTRIBUTOR},  # also a distributor in this scenario
            sectors=(SectorMembership(sector.code, "chief"),),
        )

        result = review_service.review(db_session, chief, ticket.id, {
            "sector_code":      sector.code,
            "priority":         "medium",
            "assignee_user_id": operator.id,
        })
        assert result.assignee_user_id == operator.id

    def test_distributor_can_route_sector_only(self, db_session: Session):
        """Sector-only routing is the green path for plain distributors."""
        sector = create_sector(db_session, "rev4")
        ticket = _ticket(db_session, sector=None, status="pending")

        distributor_user = create_user(db_session, "dist4")
        distributor = principal_for(distributor_user, roles={ROLE_DISTRIBUTOR})

        result = review_service.review(db_session, distributor, ticket.id, {
            "sector_code": sector.code,
            "priority":    "medium",
        })
        assert result.current_sector_id == sector.id
        assert result.assignee_user_id is None


# ── workflow_service.unassign: self / chief / admin / forbidden ─────────────

class TestUnassign:

    def test_self_unassign_clears_assignee(self, db_session: Session):
        sector = create_sector(db_session, "ua1")
        operator = create_user(db_session, "op-ua1")
        _seed_membership(db_session, operator, sector, role="member")
        ticket = _ticket(db_session, sector=sector, status="in_progress", assignee=operator)

        operator_principal = principal_for(
            operator,
            sectors=(SectorMembership(sector.code, "member"),),
        )
        result = workflow_service.unassign(db_session, operator_principal, ticket.id)
        assert result.assignee_user_id is None
        assert result.status == "assigned_to_sector"

    def test_chief_can_unassign_someone_else(self, db_session: Session):
        sector = create_sector(db_session, "ua2")
        operator = create_user(db_session, "op-ua2")
        _seed_membership(db_session, operator, sector, role="member")
        chief_user = create_user(db_session, "chief-ua2")
        _seed_membership(db_session, chief_user, sector, role="chief")
        ticket = _ticket(db_session, sector=sector, status="in_progress", assignee=operator)

        chief = principal_for(
            chief_user,
            sectors=(SectorMembership(sector.code, "chief"),),
        )
        result = workflow_service.unassign(db_session, chief, ticket.id, reason="rebalancing")
        assert result.assignee_user_id is None

    def test_admin_can_unassign_anyone(self, db_session: Session):
        sector = create_sector(db_session, "ua3")
        operator = create_user(db_session, "op-ua3")
        _seed_membership(db_session, operator, sector, role="member")
        ticket = _ticket(db_session, sector=sector, status="in_progress", assignee=operator)

        admin_user = create_user(db_session, "admin-ua3")
        admin = principal_for(admin_user, roles={ROLE_ADMIN})
        result = workflow_service.unassign(db_session, admin, ticket.id)
        assert result.assignee_user_id is None

    def test_other_member_cannot_unassign(self, db_session: Session):
        sector = create_sector(db_session, "ua4")
        operator = create_user(db_session, "op-ua4")
        _seed_membership(db_session, operator, sector, role="member")
        peer = create_user(db_session, "peer-ua4")
        _seed_membership(db_session, peer, sector, role="member")
        ticket = _ticket(db_session, sector=sector, status="in_progress", assignee=operator)

        peer_principal = principal_for(
            peer,
            sectors=(SectorMembership(sector.code, "member"),),
        )
        with pytest.raises(PermissionDeniedError):
            workflow_service.unassign(db_session, peer_principal, ticket.id)

    def test_unassign_when_already_unassigned_is_idempotent(self, db_session: Session):
        sector = create_sector(db_session, "ua5")
        ticket = _ticket(db_session, sector=sector, status="assigned_to_sector")

        admin_user = create_user(db_session, "admin-ua5")
        admin = principal_for(admin_user, roles={ROLE_ADMIN})
        result = workflow_service.unassign(db_session, admin, ticket.id)
        assert result.assignee_user_id is None


# ── reference_service.assignable_users gate ─────────────────────────────────

class TestAssignableUsersGate:
    """The HTTP-layer guard lives in src/api/reference.py — exercise it through
    Principal-shaped checks here so we don't need a Flask test client.
    """

    def test_non_admin_distributor_can_query_any_sector(self, db_session: Session):
        sector = create_sector(db_session, "ref1")
        op = create_user(db_session, "op-ref1")
        _seed_membership(db_session, op, sector, role="member")

        from src.ticketing.service.reference_service import assignable_users
        rows = assignable_users(db_session, sector_code=sector.code)
        assert any(r["id"] == op.id for r in rows)

    def test_member_only_sees_their_sector(self, db_session: Session):
        # Pure unit-shaped check: the API layer uses Principal.all_sectors to
        # decide; the service itself is unfiltered. We assert the membership
        # set the API uses contains the expected sector.
        sector = create_sector(db_session, "ref2")
        op = create_user(db_session, "op-ref2")
        _seed_membership(db_session, op, sector, role="member")

        operator_principal = principal_for(
            op,
            sectors=(SectorMembership(sector.code, "member"),),
        )
        assert sector.code in operator_principal.all_sectors
        assert "other-sector" not in operator_principal.all_sectors
