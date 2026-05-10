"""Role × capability matrix — the regression tripwire for RBAC drift.

Each row is a real seeded persona (see `docs/RBAC.md` and
`scripts/keycloak_bootstrap.py`). Each column is a sensitive capability.
The expected cell value is what `iam.rbac` should return for that pairing
on the canonical fixture ticket(s).

If the RBAC policy intentionally changes, update this matrix in lockstep —
the diff makes the policy intent reviewable in the PR.
"""
from dataclasses import dataclass
from typing import Optional

import pytest

from src.iam import rbac
from src.iam.principal import (
    ROLE_ADMIN,
    ROLE_AUDITOR,
    ROLE_DISTRIBUTOR,
    ROLE_EXTERNAL_USER,
    ROLE_INTERNAL_USER,
    Principal,
    SectorMembership,
)


# ── Personas (matching the seeded users in scripts/keycloak_bootstrap.py) ────

def _make(*, user_id: str, roles: tuple[str, ...] = (),
          memberships: tuple[SectorMembership, ...] = (),
          user_type: str = "internal", email: str | None = None) -> Principal:
    return Principal(
        user_id=user_id,
        keycloak_subject=f"kc-{user_id}",
        username=user_id,
        email=email or f"{user_id}@x",
        user_type=user_type,
        global_roles=frozenset(roles),
        sector_memberships=memberships,
    )


PERSONAS = {
    "admin":         _make(user_id="admin", roles=(ROLE_ADMIN,)),
    "auditor":       _make(user_id="auditor", roles=(ROLE_AUDITOR, ROLE_INTERNAL_USER)),
    "distributor":   _make(user_id="distributor", roles=(ROLE_DISTRIBUTOR, ROLE_INTERNAL_USER)),
    "chief_s10":     _make(user_id="chief_s10",
                            roles=(ROLE_INTERNAL_USER,),
                            memberships=(SectorMembership("s10", "chief"),)),
    "member_s10":    _make(user_id="member_s10",
                            roles=(ROLE_INTERNAL_USER,),
                            memberships=(SectorMembership("s10", "member"),)),
    "member_s2":     _make(user_id="member_s2",
                            roles=(ROLE_INTERNAL_USER,),
                            memberships=(SectorMembership("s2", "member"),)),
    "beneficiary":   _make(user_id="beneficiary", roles=(ROLE_INTERNAL_USER,)),
    "external_user": _make(user_id="external_user", roles=(ROLE_EXTERNAL_USER,),
                            user_type="external", email="ext@x"),
}


@dataclass
class FakeTicket:
    id: str = "t-1"
    status: str = "in_progress"
    beneficiary_type: str = "internal"
    requester_email: Optional[str] = None
    current_sector_code: Optional[str] = "s10"
    assignee_user_id: Optional[str] = None
    last_active_assignee_user_id: Optional[str] = None
    created_by_user_id: Optional[str] = None
    beneficiary_user_id: Optional[str] = None
    is_deleted: bool = False


# Canonical fixture ticket: routed to s10, assigned to the s10 member,
# created by `beneficiary`, internal type. This is the bread-and-butter
# operational ticket — it touches every role's "normal" code path.
def _ticket_in_s10_assigned() -> FakeTicket:
    return FakeTicket(
        status="in_progress",
        current_sector_code="s10",
        assignee_user_id="member_s10",
        last_active_assignee_user_id="member_s10",
        created_by_user_id="beneficiary",
        beneficiary_user_id="beneficiary",
    )


def _ticket_pending_unassigned() -> FakeTicket:
    return FakeTicket(
        status="pending",
        current_sector_code=None,
        assignee_user_id=None,
        created_by_user_id="beneficiary",
        beneficiary_user_id="beneficiary",
    )


# ── View ─────────────────────────────────────────────────────────────────────

class TestViewMatrix:
    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", True),
        ("distributor", False),     # not pending/assigned_to_sector
        ("chief_s10", True),
        ("member_s10", True),
        ("member_s2", False),
        ("beneficiary", True),      # creator
        ("external_user", False),
    ])
    def test_view_in_progress_s10(self, persona, expected):
        assert rbac.can_view_ticket(PERSONAS[persona], _ticket_in_s10_assigned()) is expected

    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", True),
        ("distributor", True),       # pending → distributor lane
        ("chief_s10", False),        # not yet routed
        ("member_s10", False),
        ("member_s2", False),
        ("beneficiary", True),       # creator
        ("external_user", False),
    ])
    def test_view_pending_unrouted(self, persona, expected):
        assert rbac.can_view_ticket(PERSONAS[persona], _ticket_pending_unassigned()) is expected


# ── Comments (post) — self-assignment policy in effect ──────────────────────

class TestPostPublicCommentMatrix:
    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", False),                # read-only oversight
        ("distributor", False),            # tightened: must self-assign first
        ("chief_s10", False),              # tightened
        ("member_s10", True),              # is the active assignee
        ("member_s2", False),
        ("beneficiary", True),             # creator + beneficiary user
        ("external_user", False),
    ])
    def test_post_public_assigned_s10(self, persona, expected):
        assert rbac.can_post_public_comment(
            PERSONAS[persona], _ticket_in_s10_assigned()
        ) is expected


class TestPostPrivateCommentMatrix:
    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", False),                # read access only
        ("distributor", True),             # triage lane preserved
        ("chief_s10", False),              # tightened: not assigned
        ("member_s10", True),              # active assignee
        ("member_s2", False),
        ("beneficiary", False),            # never private
        ("external_user", False),
    ])
    def test_post_private_assigned_s10(self, persona, expected):
        assert rbac.can_post_private_comment(
            PERSONAS[persona], _ticket_in_s10_assigned()
        ) is expected


# ── Status transitions (operator-side) ──────────────────────────────────────

class TestDriveStatusMatrix:
    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", False),
        ("distributor", False),             # narrow lane via cancel/assign_sector only
        ("chief_s10", False),               # tightened: must self-assign first
        ("member_s10", True),               # active assignee
        ("member_s2", False),
        ("beneficiary", False),             # uses close/reopen, not drive
        ("external_user", False),
    ])
    def test_drive_status(self, persona, expected):
        assert rbac.can_drive_status(
            PERSONAS[persona], _ticket_in_s10_assigned()
        ) is expected


class TestMarkDoneMatrix:
    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", False),
        ("distributor", False),
        ("chief_s10", False),
        ("member_s10", True),
        ("member_s2", False),
        ("beneficiary", False),
        ("external_user", False),
    ])
    def test_mark_done(self, persona, expected):
        assert rbac.can_mark_done(
            PERSONAS[persona], _ticket_in_s10_assigned()
        ) is expected


# ── Beneficiary-side close/reopen ───────────────────────────────────────────

class TestCloseReopenMatrix:
    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", False),
        ("distributor", False),
        ("chief_s10", False),
        ("member_s10", False),               # operators don't close
        ("member_s2", False),
        ("beneficiary", True),               # creator/beneficiary path
        ("external_user", False),
    ])
    def test_close(self, persona, expected):
        assert rbac.can_close(
            PERSONAS[persona], _ticket_in_s10_assigned()
        ) is expected

    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", False),
        ("distributor", False),
        ("chief_s10", False),
        ("member_s10", False),
        ("member_s2", False),
        ("beneficiary", True),
        ("external_user", False),
    ])
    def test_reopen(self, persona, expected):
        assert rbac.can_reopen(
            PERSONAS[persona], _ticket_in_s10_assigned()
        ) is expected


# ── Assignment workflow ─────────────────────────────────────────────────────

class TestAssignmentMatrix:
    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", False),
        ("distributor", True),               # primary distributor capability
        # Chief can't claim an unrouted ticket — they only act on tickets
        # already routed into their sector. Unrouted ones are the
        # distributor's domain.
        ("chief_s10", False),
        ("member_s10", False),
        ("member_s2", False),
        ("beneficiary", False),
        ("external_user", False),
    ])
    def test_assign_sector_unrouted(self, persona, expected):
        assert rbac.can_assign_sector(
            PERSONAS[persona], _ticket_pending_unassigned()
        ) is expected

    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", False),
        ("distributor", True),
        # Chief gains the capability once the ticket is in their sector.
        ("chief_s10", True),
        ("member_s10", False),
        ("member_s2", False),
        ("beneficiary", False),
        ("external_user", False),
    ])
    def test_assign_sector_already_in_s10(self, persona, expected):
        assert rbac.can_assign_sector(
            PERSONAS[persona], _ticket_in_s10_assigned()
        ) is expected

    @pytest.mark.parametrize("persona,expected", [
        # `can_assign_to_user` = admin / distributor / chief of current sector
        ("admin", True),
        ("auditor", False),
        ("distributor", True),
        ("chief_s10", True),
        ("member_s10", False),
        ("member_s2", False),
        ("beneficiary", False),
        ("external_user", False),
    ])
    def test_assign_to_user(self, persona, expected):
        assert rbac.can_assign_to_user(
            PERSONAS[persona], _ticket_in_s10_assigned()
        ) is expected


# ── Audit + admin gates ─────────────────────────────────────────────────────

class TestAdminAuditMatrix:
    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", False),
        ("distributor", False),
        ("chief_s10", False),
        ("member_s10", False),
        ("member_s2", False),
        ("beneficiary", False),
        ("external_user", False),
    ])
    def test_administer(self, persona, expected):
        assert rbac.can_administer(PERSONAS[persona]) is expected

    @pytest.mark.parametrize("persona,expected", [
        ("admin", True),
        ("auditor", True),
        ("distributor", False),
        ("chief_s10", False),
        ("member_s10", False),
        ("member_s2", False),
        ("beneficiary", False),
        ("external_user", False),
    ])
    def test_global_audit(self, persona, expected):
        assert rbac.can_view_global_audit(PERSONAS[persona]) is expected
