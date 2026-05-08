"""Unit tests for src/iam/principal.py."""
from src.iam.principal import (
    ROLE_ADMIN,
    ROLE_DISTRIBUTOR,
    Principal,
    SectorMembership,
)


def _p(**kw) -> Principal:
    base = dict(
        user_id="u-1",
        keycloak_subject="kc-1",
        username="u",
        email="u@x",
    )
    base.update(kw)
    return Principal(**base)


def test_role_helpers():
    p = _p(global_roles=frozenset({ROLE_ADMIN}))
    assert p.is_admin
    assert p.has_role(ROLE_ADMIN)
    assert p.has_any([ROLE_ADMIN, ROLE_DISTRIBUTOR])
    assert not p.is_distributor


def test_sector_helpers():
    memberships = (
        SectorMembership("s10", "member"),
        SectorMembership("s9", "chief"),
    )
    p = _p(sector_memberships=memberships)
    assert p.is_member_of("s10")
    assert not p.is_member_of("s9")
    assert p.is_chief_of("s9")
    assert p.is_in_sector("s10")
    assert p.is_in_sector("s9")
    assert p.member_sectors == {"s10"}
    assert p.chief_sectors  == {"s9"}
    assert p.all_sectors    == {"s10", "s9"}


def test_internal_external():
    assert _p(user_type="internal").is_internal
    assert _p(user_type="external").is_external
