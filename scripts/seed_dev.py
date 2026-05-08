#!/usr/bin/env python3
"""Seed local development data in Keycloak and Postgres.

Idempotent: safe to run repeatedly after `make keycloak-bootstrap` and
`make migrate`.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from scripts.keycloak_bootstrap import REALM, admin, ensure_realm, main as bootstrap_keycloak
from src.core.db import get_db
from src.iam.models import User
from src.ticketing.models import Beneficiary, Sector, SectorMembership, Ticket, TicketComment, TicketMetadata

PASSWORD = "Tickora123!"

SECTORS = [
    ("s1", "Service Desk"),
    ("s2", "Network Operations"),
    ("s3", "Infrastructure"),
    ("s4", "Applications"),
    ("s5", "Security"),
    ("s10", "Field Operations"),
]

USERS = [
    {
        "username": "admin",
        "email": "admin@tickora.local",
        "first_name": "Ana",
        "last_name": "Admin",
        "type": "internal",
        "roles": [],
        "groups": ["/tickora"],
    },
    {
        "username": "bogdan",
        "email": "bogdan@tickora.local",
        "first_name": "Bogdan",
        "last_name": "SuperAdmin",
        "type": "internal",
        "roles": [],
        "groups": ["/tickora"],
        "keycloak_subject": "93d10567-d264-4b06-948c-c1265d675845",
    },
    {
        "username": "auditor",
        "email": "auditor@tickora.local",
        "first_name": "Alex",
        "last_name": "Auditor",
        "type": "internal",
        "roles": ["tickora_auditor", "tickora_internal_user"],
        "groups": [],
    },
    {
        "username": "distributor",
        "email": "distributor@tickora.local",
        "first_name": "Daria",
        "last_name": "Distribuitor",
        "type": "internal",
        "roles": ["tickora_distributor", "tickora_internal_user"],
        "groups": [],
    },
    {
        "username": "chief.s10",
        "email": "chief.s10@tickora.local",
        "first_name": "Mihai",
        "last_name": "Chief",
        "type": "internal",
        "roles": [],
        "groups": ["/tickora/sectors/s10"],
    },
    {
        "username": "member.s10",
        "email": "member.s10@tickora.local",
        "first_name": "Ioana",
        "last_name": "Member",
        "type": "internal",
        "roles": ["tickora_sector_member", "tickora_internal_user"],
        "groups": ["/tickora/sectors/s10/members"],
    },
    {
        "username": "member.s2",
        "email": "member.s2@tickora.local",
        "first_name": "Radu",
        "last_name": "Network",
        "type": "internal",
        "roles": ["tickora_sector_member", "tickora_internal_user"],
        "groups": ["/tickora/sectors/s2/members"],
    },
    {
        "username": "beneficiary",
        "email": "beneficiary@tickora.local",
        "first_name": "Bianca",
        "last_name": "Beneficiar",
        "type": "internal",
        "roles": ["tickora_internal_user"],
        "groups": [],
    },
    {
        "username": "external.user",
        "email": "external.user@example.test",
        "first_name": "Ema",
        "last_name": "External",
        "type": "external",
        "roles": ["tickora_external_user"],
        "groups": [],
    },
]


def _kc_user(kc, spec: dict) -> str:
    username = spec["username"]
    matches = kc.get_users({"username": username, "exact": True})
    payload = {
        "username": username,
        "email": spec["email"],
        "firstName": spec["first_name"],
        "lastName": spec["last_name"],
        "enabled": True,
        "emailVerified": True,
    }
    
    fixed_id = spec.get("keycloak_subject")
    
    if matches:
        user_id = matches[0]["id"]
        kc.update_user(user_id, payload)
    else:
        if fixed_id:
            payload["id"] = fixed_id
        user_id = kc.create_user(payload, exist_ok=True)
    
    kc.set_user_password(user_id, PASSWORD, temporary=False)
    return user_id


def _assign_roles(kc, user_id: str, roles: list[str]) -> None:
    if not roles:
        return
    role_payloads = [kc.get_realm_role(role) for role in roles]
    kc.assign_realm_roles(user_id, role_payloads)


def _assign_groups(kc, user_id: str, paths: list[str]) -> None:
    for path in paths:
        group = kc.get_group_by_path(path)
        kc.group_user_add(user_id, group["id"])


def seed_keycloak() -> dict[str, str]:
    bootstrap_keycloak()
    kc = admin()
    ensure_realm(kc)
    out: dict[str, str] = {}
    for spec in USERS:
        user_id = _kc_user(kc, spec)
        _assign_roles(kc, user_id, spec["roles"])
        _assign_groups(kc, user_id, spec["groups"])
        out[spec["username"]] = user_id
        print(f"[keycloak:user] {spec['username']} / {PASSWORD}")
    return out


def _sector(db, code: str, name: str) -> Sector:
    sector = db.scalar(select(Sector).where(Sector.code == code))
    if sector is None:
        sector = Sector(code=code, name=name, description=f"Seeded {name}", is_active=True)
        db.add(sector)
        db.flush()
    else:
        sector.name = name
        sector.is_active = True
    return sector


def _user(db, spec: dict, keycloak_subject: str) -> User:
    user = db.scalar(select(User).where(User.keycloak_subject == keycloak_subject))
    if user is None:
        user = User(keycloak_subject=keycloak_subject)
        db.add(user)
    user.username = spec["username"]
    user.email = spec["email"]
    user.first_name = spec["first_name"]
    user.last_name = spec["last_name"]
    user.user_type = spec["type"]
    user.is_active = True
    db.flush()
    return user


def _beneficiary(db, user: User) -> Beneficiary:
    beneficiary = db.scalar(select(Beneficiary).where(Beneficiary.user_id == user.id))
    if beneficiary is None:
        beneficiary = Beneficiary(user_id=user.id, beneficiary_type=user.user_type)
        db.add(beneficiary)
    beneficiary.first_name = user.first_name
    beneficiary.last_name = user.last_name
    beneficiary.email = user.email
    db.flush()
    return beneficiary


def _membership(db, user: User, sector: Sector, role: str) -> None:
    membership = db.scalar(
        select(SectorMembership).where(
            SectorMembership.user_id == user.id,
            SectorMembership.sector_id == sector.id,
            SectorMembership.membership_role == role,
        )
    )
    if membership is None:
        membership = SectorMembership(
            user_id=user.id,
            sector_id=sector.id,
            membership_role=role,
            is_active=True,
        )
        db.add(membership)
    membership.is_active = True


def _ticket(
    db,
    *,
    code: str,
    beneficiary: Beneficiary,
    created_by: User,
    sector: Sector | None,
    assignee: User | None,
    title: str,
    body: str,
    status: str,
    priority: str,
) -> Ticket:
    ticket = db.scalar(select(Ticket).where(Ticket.ticket_code == code))
    if ticket is None:
        ticket = Ticket(ticket_code=code, txt=body)
        db.add(ticket)
    ticket.beneficiary_id = beneficiary.id
    ticket.beneficiary_type = beneficiary.beneficiary_type
    ticket.created_by_user_id = created_by.id
    ticket.requester_first_name = beneficiary.first_name
    ticket.requester_last_name = beneficiary.last_name
    ticket.requester_email = beneficiary.email
    ticket.current_sector_id = sector.id if sector else None
    ticket.assignee_user_id = assignee.id if assignee else None
    ticket.last_active_assignee_user_id = assignee.id if assignee else None
    ticket.title = title
    ticket.txt = body
    ticket.category = "network_issue" if sector and sector.code == "s2" else "operations"
    ticket.type = "incident"
    ticket.status = status
    ticket.priority = priority
    ticket.is_deleted = False
    db.flush()
    return ticket


def _comment(db, ticket: Ticket, author: User, body: str, visibility: str) -> None:
    exists = db.scalar(
        select(TicketComment).where(
            TicketComment.ticket_id == ticket.id,
            TicketComment.author_user_id == author.id,
            TicketComment.body == body,
        )
    )
    if exists is None:
        db.add(TicketComment(
            ticket_id=ticket.id,
            author_user_id=author.id,
            body=body,
            visibility=visibility,
            comment_type="user_comment",
        ))


def _metadata(db, ticket: Ticket, key: str, value: str, label: str | None = None) -> None:
    meta = db.scalar(
        select(TicketMetadata).where(
            TicketMetadata.ticket_id == ticket.id,
            TicketMetadata.key == key,
        )
    )
    if meta is None:
        meta = TicketMetadata(ticket_id=ticket.id, key=key)
        db.add(meta)
    meta.value = value
    meta.label = label
    db.flush()


def seed_database(subjects: dict[str, str]) -> None:
    with get_db() as db:
        sectors = {code: _sector(db, code, name) for code, name in SECTORS}
        users = {spec["username"]: _user(db, spec, subjects[spec["username"]]) for spec in USERS}
        beneficiaries = {name: _beneficiary(db, user) for name, user in users.items()}

        _membership(db, users["chief.s10"], sectors["s10"], "chief")
        _membership(db, users["chief.s10"], sectors["s10"], "member")
        _membership(db, users["member.s10"], sectors["s10"], "member")
        _membership(db, users["member.s2"], sectors["s2"], "member")

        t1 = _ticket(
            db,
            code="TK-SEED-000001",
            beneficiary=beneficiaries["beneficiary"],
            created_by=users["beneficiary"],
            sector=None,
            assignee=None,
            title="Cannot access internal portal",
            body="The internal portal returns a timeout from the office network.",
            status="pending",
            priority="high",
        )
        t2 = _ticket(
            db,
            code="TK-SEED-000002",
            beneficiary=beneficiaries["beneficiary"],
            created_by=users["beneficiary"],
            sector=sectors["s10"],
            assignee=users["member.s10"],
            title="Field terminal replacement",
            body="A field terminal is damaged and needs replacement.",
            status="in_progress",
            priority="medium",
        )
        t3 = _ticket(
            db,
            code="TK-SEED-000003",
            beneficiary=beneficiaries["external.user"],
            created_by=users["external.user"],
            sector=sectors["s2"],
            assignee=users["member.s2"],
            title="External VPN intermittent drops",
            body="External beneficiary reports VPN drops every 10 minutes.",
            status="assigned_to_sector",
            priority="critical",
        )
        _comment(db, t2, users["member.s10"], "We started replacement logistics.", "public")
        _comment(db, t2, users["chief.s10"], "Check stock before committing ETA.", "private")
        _comment(db, t3, users["member.s2"], "Initial packet-loss checks are underway.", "public")

        _metadata(db, t1, "importance", "vip", "Importance Level")
        _metadata(db, t1, "platform", "mobile", "Target Platform")
        _metadata(db, t2, "importance", "standard", "Importance Level")
        _metadata(db, t3, "importance", "vip", "Importance Level")
        
        print("[db] sectors, users, memberships, beneficiaries, tickets, comments, metadata seeded")


def main() -> int:
    subjects = seed_keycloak()
    seed_database(subjects)
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
