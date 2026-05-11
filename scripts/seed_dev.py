#!/usr/bin/env python3
"""Seed local development data — Keycloak realm + Postgres tickets/users.

Designed to run on a **fresh deployment**:
  1. Runs Alembic migrations to head if tables are missing.
  2. Bootstraps the Keycloak realm + clients + roles + sector group tree.
  3. Creates the seeded users in Keycloak with their realm roles + group
     memberships.
  4. Mirrors users / sectors / memberships into Postgres.
  5. Generates ~1k high-fidelity tickets with status history,
     conversations, metadata, and a sample dashboard per user.

Idempotent: re-running drops + re-seeds the **ticketing** content but
leaves Keycloak users intact (their IDs stay stable so re-seeding the
DB doesn't break previous logins).

Tunables via env:
  * `SEED_TICKETS`        — number of tickets to generate (default 1000).
  * `SEED_RUN_MIGRATIONS` — `1` (default) to run alembic upgrade head first.
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from faker import Faker
from sqlalchemy import inspect, text

from scripts.keycloak_bootstrap import (
    REALM_ROLES,
    admin,
    ensure_realm,
    main as bootstrap_keycloak,
)
from src.core.db import get_db, get_engine
from src.iam.models import User
from src.ticketing.models import (
    Beneficiary,
    Category,
    CustomDashboard,
    DashboardWidget,
    MetadataKeyDefinition,
    Notification,
    Sector,
    SectorMembership,
    Subcategory,
    Ticket,
    TicketAssignmentHistory,
    TicketComment,
    TicketSectorHistory,
    TicketStatusHistory,
)
from src.ticketing.service import dashboard_service
from src.ticketing.state_machine import ALL_STATUSES, DONE_STATUSES

fake = Faker()
PASSWORD = "Tickora123!"

SECTORS = [
    ("s1",  "Service Desk"),
    ("s2",  "Network Operations"),
    ("s3",  "Infrastructure"),
    ("s4",  "Applications"),
    ("s5",  "Security"),
    ("s6",  "Database Administration"),
    ("s7",  "Cloud Services"),
    ("s8",  "DevOps & CI/CD"),
    ("s9",  "Quality Assurance"),
    ("s10", "Field Operations"),
]

# `groups` here are the Keycloak group paths (created by
# `keycloak_bootstrap.py`). `roles` are the realm roles. Both are
# applied at user-create time so every user can immediately log in
# with the right access.
USERS = [
    {"username": "admin",         "email": "admin@tickora.local",         "first_name": "Ana",     "last_name": "Admin",        "type": "internal",
     "roles": ["tickora_admin", "tickora_internal_user"],
     "groups": ["/tickora"]},
    {"username": "bogdan",        "email": "bogdan@tickora.local",        "first_name": "Bogdan",  "last_name": "SuperAdmin",   "type": "internal",
     "roles": ["tickora_admin", "tickora_internal_user"],
     "groups": ["/tickora"]},
    {"username": "auditor",       "email": "auditor@tickora.local",       "first_name": "Alex",    "last_name": "Auditor",      "type": "internal",
     "roles": ["tickora_auditor", "tickora_internal_user"],
     "groups": []},
    {"username": "distributor",   "email": "distributor@tickora.local",   "first_name": "Daria",   "last_name": "Distribuitor", "type": "internal",
     "roles": ["tickora_distributor", "tickora_internal_user"],
     "groups": []},
    {"username": "chief.s10",     "email": "chief.s10@tickora.local",     "first_name": "Mihai",   "last_name": "Chief",        "type": "internal",
     "roles": ["tickora_internal_user"],
     "groups": ["/tickora/sectors/s10"]},
    {"username": "member.s10",    "email": "member.s10@tickora.local",    "first_name": "Ioana",   "last_name": "Member",       "type": "internal",
     "roles": ["tickora_internal_user"],
     "groups": ["/tickora/sectors/s10/member"]},
    {"username": "member.s2",     "email": "member.s2@tickora.local",     "first_name": "Radu",    "last_name": "Network",      "type": "internal",
     "roles": ["tickora_internal_user"],
     "groups": ["/tickora/sectors/s2/member"]},
    {"username": "beneficiary",   "email": "beneficiary@tickora.local",   "first_name": "Bianca",  "last_name": "Beneficiar",   "type": "internal",
     "roles": ["tickora_internal_user"],
     "groups": ["/tickora/beneficiaries/internal"]},
    {"username": "ben.int.1",     "email": "ben.int.1@tickora.local",     "first_name": "Ion",     "last_name": "Vasile",       "type": "internal",
     "roles": ["tickora_internal_user"],
     "groups": ["/tickora/beneficiaries/internal"]},
    {"username": "ben.int.2",     "email": "ben.int.2@tickora.local",     "first_name": "Maria",   "last_name": "Ionescu",      "type": "internal",
     "roles": ["tickora_internal_user"],
     "groups": ["/tickora/beneficiaries/internal"]},
    {"username": "external.user", "email": "external.user@example.test",  "first_name": "Eric",    "last_name": "External",     "type": "external",
     "roles": ["tickora_external_user"],
     "groups": ["/tickora/beneficiaries/external"]},
    {"username": "ben.ext.1",     "email": "ben.ext.1@example.test",      "first_name": "George",  "last_name": "Popescu",      "type": "external",
     "roles": ["tickora_external_user"],
     "groups": ["/tickora/beneficiaries/external"]},
    {"username": "ben.ext.2",     "email": "ben.ext.2@example.test",      "first_name": "Elena",   "last_name": "Radu",         "type": "external",
     "roles": ["tickora_external_user"],
     "groups": ["/tickora/beneficiaries/external"]},
]


# ── Migrations ──────────────────────────────────────────────────────────────

def _tables_exist() -> bool:
    """Cheap check — if `users` exists, the schema has been migrated."""
    try:
        return inspect(get_engine()).has_table("users")
    except Exception:
        return False


def run_migrations_if_needed() -> None:
    """Run `alembic upgrade head` unless the user opts out via env.

    On a fresh DB the schema is empty; on a re-run alembic just stamps
    the head with no-op steps. Failure here is fatal — the rest of the
    script depends on the schema existing.
    """
    if os.getenv("SEED_RUN_MIGRATIONS", "1") not in ("1", "true", "True"):
        return
    if _tables_exist():
        # Even when tables exist, run alembic upgrade so any new
        # migrations land before the seed touches the schema.
        print("[migrate] running `alembic upgrade head` (incremental)…")
    else:
        print("[migrate] empty schema — running `alembic upgrade head`…")
    res = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(ROOT),
        check=False,
    )
    if res.returncode != 0:
        raise SystemExit(f"alembic upgrade failed (exit {res.returncode})")


# ── Keycloak ────────────────────────────────────────────────────────────────

def _assign_roles(kc, user_id: str, role_names: list[str]) -> None:
    """Assign realm roles to a user. Skips roles that don't exist yet."""
    if not role_names:
        return
    available = {r["name"]: r for r in kc.get_realm_roles()}
    roles = [available[n] for n in role_names if n in available]
    missing = [n for n in role_names if n not in available]
    if missing:
        print(f"[kc:roles] missing realm roles, skipping: {missing}")
    if roles:
        kc.assign_realm_roles(user_id=user_id, roles=roles)


def _assign_groups(kc, user_id: str, group_paths: list[str]) -> None:
    """Add a user to each Keycloak group path. Idempotent."""
    if not group_paths:
        return
    current = {g["path"] for g in kc.get_user_groups(user_id=user_id)}
    for path in group_paths:
        if path in current:
            continue
        try:
            group = kc.get_group_by_path(path)
        except Exception:
            print(f"[kc:groups] path missing, skipping: {path}")
            continue
        kc.group_user_add(user_id, group["id"])


def seed_keycloak() -> dict[str, str]:
    """Boot the realm + create/update each user. Returns username → kc id."""
    bootstrap_keycloak()
    kc = admin()
    ensure_realm(kc)
    out: dict[str, str] = {}
    for spec in USERS:
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
        if matches:
            user_id = matches[0]["id"]
            kc.update_user(user_id, payload)
            print(f"[kc:user] updated '{username}'")
        else:
            user_id = kc.create_user(payload, exist_ok=True)
            print(f"[kc:user] created '{username}'")
        kc.set_user_password(user_id, PASSWORD, temporary=False)
        _assign_roles(kc, user_id, spec.get("roles", []))
        _assign_groups(kc, user_id, spec.get("groups", []))
        out[username] = user_id
    return out


# ── Database ────────────────────────────────────────────────────────────────

def _truncate_safely(db, tables: list[str]) -> None:
    """`TRUNCATE … CASCADE` but only for tables that actually exist.

    On a fresh DB after migrations all tables exist; on partial schemas
    this prevents a single missing table from poisoning the whole reset.
    """
    insp = inspect(db.connection())
    present = [t for t in tables if insp.has_table(t)]
    if not present:
        return
    db.execute(text(f"TRUNCATE {', '.join(present)} CASCADE"))


def seed_database(subjects: dict[str, str]) -> None:
    n_tickets = int(os.getenv("SEED_TICKETS", "1000"))
    with get_db() as db:
        print("[db] resetting and seeding infrastructure…")
        _truncate_safely(db, [
            "ticket_watchers",
            "ticket_links",
            "notifications",
            "custom_dashboards",
            "dashboard_widgets",
            "system_settings",
            "metadata_key_definitions",
            "ticket_metadatas",
            "ticket_comments",
            "ticket_status_history",
            "ticket_sector_history",
            "ticket_assignment_history",
            "ticket_assignees",
            "ticket_sectors",
            "tickets",
            "beneficiaries",
            "sector_memberships",
            "sectors",
            "subcategories",
            "categories",
            "users",
        ])

        # Widget catalogue is idempotent — the call upserts rows into
        # `widget_definitions` for every type the auto-configurator can
        # produce. Required for `auto_configure_dashboard` below.
        dashboard_service.sync_widget_catalogue(db)

        db.add(MetadataKeyDefinition(key="environment",
                                     label="Environment",
                                     value_type="enum",
                                     options=["prod", "stage", "dev"]))

        # Categories
        categories_spec = [
            {
                "code": "infra",
                "name": "Infrastructure",
                "subcategories": [
                    {"code": "network", "name": "Network Connectivity"},
                    {"code": "hardware", "name": "Hardware Failure"},
                    {"code": "datacenter", "name": "Datacenter Access"},
                ]
            },
            {
                "code": "apps",
                "name": "Applications",
                "subcategories": [
                    {"code": "bug", "name": "Software Bug"},
                    {"code": "access", "name": "Access Request"},
                    {"code": "feature", "name": "Feature Request"},
                ]
            },
            {
                "code": "security",
                "name": "Security",
                "subcategories": [
                    {"code": "incident", "name": "Security Incident"},
                    {"code": "audit", "name": "Audit Request"},
                ]
            }
        ]
        all_subcategories = []
        for c_spec in categories_spec:
            c = Category(code=c_spec["code"], name=c_spec["name"])
            db.add(c)
            db.flush()
            for s_spec in c_spec["subcategories"]:
                s = Subcategory(category_id=c.id, code=s_spec["code"], name=s_spec["name"])
                db.add(s)
                all_subcategories.append(s)
        db.flush()

        # Sectors keyed by code so memberships can look them up.
        sectors = {code: Sector(code=code, name=name, description=f"Seeded {name}", is_active=True)
                   for code, name in SECTORS}
        db.add_all(sectors.values())
        db.flush()

        # Users (mirrored from Keycloak by stable subject)
        users_by_username: dict[str, User] = {}
        for spec in USERS:
            u = User(
                keycloak_subject=subjects[spec["username"]],
                username=spec["username"],
                email=spec["email"],
                first_name=spec["first_name"],
                last_name=spec["last_name"],
                user_type=spec["type"],
                is_active=True,
            )
            db.add(u)
            users_by_username[spec["username"]] = u
        db.flush()
        users = list(users_by_username.values())

        beneficiaries = [
            Beneficiary(user_id=u.id,
                        beneficiary_type=u.user_type,
                        first_name=u.first_name,
                        last_name=u.last_name,
                        email=u.email)
            for u in users
        ]
        db.add_all(beneficiaries)
        db.flush()

        # Memberships — mirror the Keycloak group tree into the local DB so
        # the principal hydrator can answer offline if KC is unreachable.
        for spec in USERS:
            user = users_by_username[spec["username"]]
            for path in spec.get("groups", []):
                # Path shapes:
                #   /tickora                            — full platform access (no row)
                #   /tickora/sectors/<code>             — chief + member
                #   /tickora/sectors/<code>/members     — member only
                #   /tickora/sectors/<code>/chiefs      — chief only
                parts = [p for p in path.split("/") if p]
                if len(parts) >= 3 and parts[0] == "tickora" and parts[1] == "sectors":
                    code = parts[2]
                    sector = sectors.get(code)
                    if sector is None:
                        continue
                    if len(parts) == 3:
                        # Bare /tickora/sectors/<code> → chief role only.
                        db.add(SectorMembership(
                            user_id=user.id, sector_id=sector.id,
                            membership_role="chief", is_active=True,
                        ))
                    else:
                        role = "chief" if parts[3].startswith("chief") else "member"
                        db.add(SectorMembership(
                            user_id=user.id, sector_id=sector.id,
                            membership_role=role, is_active=True,
                        ))

        # Tickets
        print(f"[db] seeding {n_tickets:,} tickets with status history + comments…")
        now = datetime.now(timezone.utc)
        internal_users = [u for u in users if u.user_type == "internal"]
        priorities = ["low", "medium", "high", "critical"]

        for i in range(1, n_tickets + 1):
            created_at = now - timedelta(days=random.randint(0, 90), hours=random.randint(0, 23))
            status = random.choice(list(ALL_STATUSES))
            ben = random.choice(beneficiaries)
            subcat = random.choice(all_subcategories)

            t = Ticket(
                ticket_code=f"TK-SEED-{i:06d}",
                title=fake.sentence(nb_words=6),
                txt=fake.paragraph(nb_sentences=3),
                status=status,
                priority=random.choice(priorities),
                category_id=subcat.category_id,
                subcategory_id=subcat.id,
                beneficiary_id=ben.id,
                beneficiary_type=ben.beneficiary_type,
                requester_first_name=ben.first_name,
                requester_last_name=ben.last_name,
                requester_email=ben.email,
                created_at=created_at,
                updated_at=created_at,
                reopened_count=0,
            )
            db.add(t)
            db.flush()

            db.add(TicketStatusHistory(ticket_id=t.id, old_status=None,
                                       new_status="pending", created_at=created_at))

            curr_time = created_at + timedelta(minutes=random.randint(5, 120))
            if status != "pending":
                sec = random.choice(list(sectors.values()))
                t.current_sector_id = sec.id
                db.add(TicketSectorHistory(ticket_id=t.id, old_sector_id=None,
                                           new_sector_id=sec.id, created_at=curr_time))
                if status != "assigned_to_sector":
                    assignee = random.choice(internal_users)
                    t.assignee_user_id = assignee.id
                    db.add(TicketAssignmentHistory(
                        ticket_id=t.id, old_assignee_user_id=None,
                        new_assignee_user_id=assignee.id,
                        created_at=curr_time + timedelta(minutes=10),
                    ))
                    db.add(TicketStatusHistory(
                        ticket_id=t.id, old_status="pending", new_status="in_progress",
                        created_at=curr_time + timedelta(minutes=15),
                    ))

            for j in range(random.randint(0, 5)):
                author = random.choice(users)
                db.add(TicketComment(
                    ticket_id=t.id, author_user_id=author.id,
                    body=fake.sentence(), visibility="public",
                    created_at=curr_time + timedelta(hours=j + 1),
                ))

            if status in DONE_STATUSES:
                res_time = curr_time + timedelta(days=random.randint(1, 5))
                t.done_at = res_time
                t.updated_at = res_time
                db.add(TicketStatusHistory(
                    ticket_id=t.id, old_status="in_progress", new_status="done",
                    created_at=res_time,
                ))

            if i % 20 == 0:
                db.add(Notification(
                    user_id=random.choice(users).id, type="ticket_created",
                    title="Ticket created", body=f"New ticket: {t.ticket_code}",
                    ticket_id=t.id,
                ))

        # One auto-configured dashboard per user — exercises the new
        # role-aware recipes so admins / chiefs / members each see a
        # different starting layout.
        from src.iam.principal import Principal, SectorMembership as PSM
        for spec in USERS:
            u = users_by_username[spec["username"]]
            d = CustomDashboard(owner_user_id=u.id, title="My Operations",
                                description="Auto-generated by seed_dev.py")
            db.add(d)
            db.flush()
            try:
                memberships = []
                has_root = False
                for path in spec.get("groups", []):
                    if path == "/tickora":
                        has_root = True
                        continue
                    parts = [p for p in path.split("/") if p]
                    if len(parts) >= 3 and parts[0] == "tickora" and parts[1] == "sectors":
                        code = parts[2]
                        if len(parts) == 3:
                            memberships.append(PSM(sector_code=code, role="chief"))
                            memberships.append(PSM(sector_code=code, role="member"))
                        else:
                            role = "chief" if parts[3].startswith("chief") else "member"
                            memberships.append(PSM(sector_code=code, role=role))

                principal = Principal(
                    user_id=u.id,
                    keycloak_subject=u.keycloak_subject,
                    username=u.username,
                    email=u.email,
                    first_name=u.first_name,
                    last_name=u.last_name,
                    user_type=u.user_type,
                    global_roles=frozenset(spec.get("roles", [])),
                    sector_memberships=tuple(memberships),
                    has_root_group=has_root,
                )
                dashboard_service.auto_configure_dashboard(
                    db, principal, d.id, mode="replace",
                )
            except Exception as exc:
                # Best effort — a misconfigured user shouldn't blow up the seed.
                print(f"[seed] auto_configure failed for {u.username}: {exc}")
                db.add(DashboardWidget(
                    dashboard_id=d.id, type="welcome_banner",
                    title="Welcome", x=0, y=0, w=4, h=3, config={},
                ))

        db.commit()
        print(f"[db] seed complete ({n_tickets:,} tickets, {len(users)} users, {len(sectors)} sectors)")


def main() -> int:
    run_migrations_if_needed()
    subjects = seed_keycloak()
    seed_database(subjects)
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
