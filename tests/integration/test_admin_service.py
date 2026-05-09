from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from src.core.errors import PermissionDeniedError, ValidationError
from src.iam.principal import ROLE_ADMIN
from src.ticketing.service import admin_service

from .conftest import create_sector, create_user, principal_for


def test_admin_can_grant_membership_and_see_hierarchy(db_session: Session):
    admin_user = create_user(db_session, "admin-service")
    target = create_user(db_session, "operator-service")
    sector = create_sector(db_session, "adm1")
    admin = principal_for(admin_user, roles={ROLE_ADMIN})

    membership = admin_service.grant_membership(db_session, admin, target.id, sector.code, "chief")

    assert membership["user_id"] == target.id
    assert membership["sector_code"] == "adm1"
    assert membership["role"] == "chief"
    hierarchy = admin_service.group_hierarchy(db_session, admin)
    sector_node = hierarchy["children"][0]["children"][0]
    assert sector_node["key"] == "sector:adm1"
    assert sector_node["children"][0]["children"][0]["user"]["id"] == target.id


def test_admin_can_list_sectors_with_membership_counts(db_session: Session):
    admin_user = create_user(db_session, "admin-sector-list")
    target = create_user(db_session, "operator-sector-list")
    sector = create_sector(db_session, "adm2")
    admin = principal_for(admin_user, roles={ROLE_ADMIN})
    admin_service.grant_membership(db_session, admin, target.id, sector.code, "member")

    sectors = admin_service.list_sectors(db_session, admin)

    assert sectors == [{
        "id": sector.id,
        "code": "adm2",
        "name": "Sector ADM2",
        "description": None,
        "is_active": True,
        "created_at": sector.created_at.isoformat(),
        "updated_at": sector.updated_at.isoformat(),
        "membership_count": 1,
    }]


def test_admin_service_rejects_non_admin(db_session: Session):
    user = create_user(db_session, "not-admin-service")
    principal = principal_for(user)

    with pytest.raises(PermissionDeniedError):
        admin_service.list_sectors(db_session, principal)


def test_admin_can_manage_sla_policy(db_session: Session):
    admin_user = create_user(db_session, "sla-admin-service")
    admin = principal_for(admin_user, roles={ROLE_ADMIN})

    policy = admin_service.upsert_sla_policy(db_session, admin, {
        "name": "Critical response",
        "priority": "critical",
        "first_response_minutes": 15,
        "resolution_minutes": 240,
        "is_active": True,
    })

    assert policy["priority"] == "critical"
    assert policy["first_response_minutes"] == 15
    assert admin_service.sla_policies(db_session, admin)[0]["name"] == "Critical response"


def test_sla_policy_requires_positive_minutes(db_session: Session):
    admin_user = create_user(db_session, "sla-admin-invalid")
    admin = principal_for(admin_user, roles={ROLE_ADMIN})

    with pytest.raises(ValidationError):
        admin_service.upsert_sla_policy(db_session, admin, {
            "name": "Invalid",
            "priority": "high",
            "first_response_minutes": 0,
            "resolution_minutes": 120,
        })
