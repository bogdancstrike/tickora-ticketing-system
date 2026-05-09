#!/usr/bin/env python3
"""Seed local development data in Keycloak and Postgres.

Idempotent: safe to run repeatedly after `make keycloak-bootstrap` and
`make migrate`.
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from faker import Faker
from sqlalchemy import select, text
from scripts.keycloak_bootstrap import DEPRECATED_REALM_ROLES, REALM, REALM_ROLES, admin, ensure_realm, main as bootstrap_keycloak
from src.core.db import get_db
from src.iam.models import User
from src.ticketing.models import Beneficiary, Sector, SectorMembership, Ticket, TicketComment, TicketMetadata, TicketStatusHistory
from src.ticketing.service import dashboard_service
from src.ticketing.state_machine import ALL_STATUSES, ACTIVE_STATUSES

fake = Faker()
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
        "roles": ["tickora_internal_user"],
        "groups": ["/tickora/sectors/s10/members"],
    },
    {
        "username": "member.s2",
        "email": "member.s2@tickora.local",
        "first_name": "Radu",
        "last_name": "Network",
        "type": "internal",
        "roles": ["tickora_internal_user"],
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

def _sync_roles(kc, user_id: str, roles: list[str]) -> None:
    managed = set(REALM_ROLES + DEPRECATED_REALM_ROLES)
    desired = set(roles)
    current = {role["name"]: role for role in kc.get_realm_roles_of_user(user_id) if role.get("name") in managed}
    to_remove = [payload for name, payload in current.items() if name not in desired]
    if to_remove:
        kc.delete_realm_roles_of_user(user_id, to_remove)
    to_add = [kc.get_realm_role(role) for role in sorted(desired - set(current))]
    if to_add:
        kc.assign_realm_roles(user_id, to_add)

def _sync_groups(kc, user_id: str, paths: list[str]) -> None:
    desired = set(paths)
    current = {group.get("path"): group for group in kc.get_user_groups(user_id) if (group.get("path") or "").startswith("/tickora")}
    for path, group in current.items():
        if path not in desired:
            kc.group_user_remove(user_id, group["id"])
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
        _sync_roles(kc, user_id, spec["roles"])
        _sync_groups(kc, user_id, spec["groups"])
        out[spec["username"]] = user_id
    return out

def _sector(db, code: str, name: str) -> Sector:
    sector = db.scalar(select(Sector).where(Sector.code == code))
    if sector is None:
        sector = Sector(code=code, name=name, description=f"Seeded {name}", is_active=True)
        db.add(sector)
        db.flush()
    return sector

def _user(db, spec: dict, keycloak_subject: str) -> User:
    user = db.scalar(select(User).where(User.keycloak_subject == keycloak_subject))
    if user is None:
        user = User(keycloak_subject=keycloak_subject)
        db.add(user)
    user.username, user.email, user.first_name, user.last_name = spec["username"], spec["email"], spec["first_name"], spec["last_name"]
    user.user_type, user.is_active = spec["type"], True
    db.flush()
    return user

def _beneficiary(db, user: User) -> Beneficiary:
    ben = db.scalar(select(Beneficiary).where(Beneficiary.user_id == user.id))
    if ben is None:
        ben = Beneficiary(user_id=user.id, beneficiary_type=user.user_type)
        db.add(ben)
    ben.first_name, ben.last_name, ben.email = user.first_name, user.last_name, user.email
    db.flush()
    return ben

def _membership(db, user: User, sector: Sector, role: str) -> None:
    m = db.scalar(select(SectorMembership).where(SectorMembership.user_id == user.id, SectorMembership.sector_id == sector.id, SectorMembership.membership_role == role))
    if m is None:
        db.add(SectorMembership(user_id=user.id, sector_id=sector.id, membership_role=role, is_active=True))
    else:
        m.is_active = True

def seed_database(subjects: dict[str, str]) -> None:
    with get_db() as db:
        dashboard_service.sync_widget_catalogue(db)
        sectors = [ _sector(db, code, name) for code, name in SECTORS ]
        users = [ _user(db, spec, subjects[spec["username"]]) for spec in USERS ]
        beneficiaries = [ _beneficiary(db, u) for u in users ]
        
        for u in users:
            if u.username == "chief.s10": _membership(db, u, sectors[5], "chief")
            if u.username in ["member.s10", "chief.s10"]: _membership(db, u, sectors[5], "member")
            if u.username == "member.s2": _membership(db, u, sectors[1], "member")
        
        db.execute(text("TRUNCATE tickets, ticket_comments, ticket_status_history, ticket_metadata CASCADE"))
        db.commit()

    with get_db() as db:
        print(f"[db] seeding 500 tickets...")
        now = datetime.now(timezone.utc)
        all_st = list(ALL_STATUSES)
        priorities = ["low", "medium", "high", "critical"]
        categories = ["network", "hardware", "software", "access", "other"]
        
        # Pre-fetch some data
        sec_ids = [s.id for s in sectors]
        ben_objs = beneficiaries
        internal_users = [u for u in users if u.user_type == "internal"]
        
        for i in range(1, 501):
            created_at = now - timedelta(days=random.randint(0, 30), hours=random.randint(0, 23))
            status = random.choice(all_st)
            priority = random.choice(priorities)
            ben = random.choice(ben_objs)
            creator = random.choice(internal_users) if ben.beneficiary_type == "internal" else None
            
            sector_id = random.choice(sec_ids) if status != "pending" else None
            assignee = random.choice(internal_users) if status in ["in_progress", "done", "closed"] else None
            
            finished_at = None
            if status in ["done", "closed"]:
                finished_at = created_at + timedelta(hours=random.randint(1, 48))

            t = Ticket(
                ticket_code=f"TK-MOCK-{i:06d}",
                title=fake.sentence(nb_words=6),
                txt=fake.paragraph(nb_sentences=3),
                status=status,
                priority=priority,
                category=random.choice(categories),
                beneficiary_id=ben.id,
                beneficiary_type=ben.beneficiary_type,
                created_by_user_id=creator.id if creator else None,
                current_sector_id=sector_id,
                assignee_user_id=assignee.id if assignee else None,
                created_at=created_at,
                updated_at=finished_at or created_at,
                done_at=finished_at if status == "done" else None,
                closed_at=finished_at if status == "closed" else None,
                requester_email=ben.email,
                requester_first_name=ben.first_name,
                requester_last_name=ben.last_name,
            )
            db.add(t)
            db.flush()
            
            # History
            db.add(TicketStatusHistory(ticket_id=t.id, old_status=None, new_status="pending", created_at=created_at))
            if status != "pending":
                db.add(TicketStatusHistory(ticket_id=t.id, old_status="pending", new_status=status, created_at=created_at + timedelta(minutes=random.randint(5, 60))))
            
            # Comments
            if random.random() > 0.5:
                for _ in range(random.randint(1, 3)):
                    author = random.choice(users)
                    db.add(TicketComment(ticket_id=t.id, author_user_id=author.id, body=fake.sentence(), visibility=random.choice(["public", "private"]), comment_type="user_comment", created_at=created_at + timedelta(hours=random.randint(1, 5))))
            
            # Metadata
            if random.random() > 0.7:
                db.add(TicketMetadata(ticket_id=t.id, key="environment", value=random.choice(["prod", "dev", "stage"])))

        db.commit()
        print("[db] 500 mock tickets seeded successfully")

def main() -> int:
    subjects = seed_keycloak()
    seed_database(subjects)
    print("done.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
