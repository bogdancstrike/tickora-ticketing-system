#!/usr/bin/env python3
"""Seed local development data in Keycloak and Postgres.

Overhauled version: mocks notifications, dashboards, system_settings, 
detailed conversations, and historical transitions.
"""
from __future__ import annotations

import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from faker import Faker
from sqlalchemy import select, text
from scripts.keycloak_bootstrap import DEPRECATED_REALM_ROLES, REALM, REALM_ROLES, admin, ensure_realm, main as bootstrap_keycloak
from src.core.db import get_db
from src.iam.models import User
from src.ticketing.models import (
    Beneficiary, Sector, SectorMembership, Ticket, TicketComment, 
    TicketMetadata, TicketStatusHistory, TicketSectorHistory, 
    TicketAssignmentHistory, Notification, SystemSetting, MetadataKeyDefinition,
    CustomDashboard, DashboardWidget
)
from src.ticketing.state_machine import ALL_STATUSES, ACTIVE_STATUSES, DONE_STATUSES

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
    {"username": "admin", "email": "admin@tickora.local", "first_name": "Ana", "last_name": "Admin", "type": "internal", "roles": ["tickora_admin", "tickora_internal_user"], "groups": ["/tickora"]},
    {"username": "bogdan", "email": "bogdan@tickora.local", "first_name": "Bogdan", "last_name": "SuperAdmin", "type": "internal", "roles": ["tickora_admin", "tickora_internal_user"], "groups": ["/tickora"], "keycloak_subject": "93d10567-d264-4b06-948c-c1265d675845"},
    {"username": "auditor", "email": "auditor@tickora.local", "first_name": "Alex", "last_name": "Auditor", "type": "internal", "roles": ["tickora_auditor", "tickora_internal_user"], "groups": []},
    {"username": "distributor", "email": "distributor@tickora.local", "first_name": "Daria", "last_name": "Distribuitor", "type": "internal", "roles": ["tickora_distributor", "tickora_internal_user"], "groups": []},
    {"username": "chief.s10", "email": "chief.s10@tickora.local", "first_name": "Mihai", "last_name": "Chief", "type": "internal", "roles": ["tickora_internal_user"], "groups": ["/tickora/sectors/s10"]},
    {"username": "member.s10", "email": "member.s10@tickora.local", "first_name": "Ioana", "last_name": "Member", "type": "internal", "roles": ["tickora_internal_user"], "groups": ["/tickora/sectors/s10/members"]},
    {"username": "member.s2", "email": "member.s2@tickora.local", "first_name": "Radu", "last_name": "Network", "type": "internal", "roles": ["tickora_internal_user"], "groups": ["/tickora/sectors/s2/members"]},
    {"username": "beneficiary", "email": "beneficiary@tickora.local", "first_name": "Bianca", "last_name": "Beneficiar", "type": "internal", "roles": ["tickora_internal_user"], "groups": []},
]

def seed_keycloak() -> dict[str, str]:
    bootstrap_keycloak()
    kc = admin()
    ensure_realm(kc)
    out: dict[str, str] = {}
    for spec in USERS:
        username = spec["username"]
        matches = kc.get_users({"username": username, "exact": True})
        payload = {"username": username, "email": spec["email"], "firstName": spec["first_name"], "lastName": spec["last_name"], "enabled": True, "emailVerified": True}
        if matches:
            user_id = matches[0]["id"]
            kc.update_user(user_id, payload)
        else:
            if spec.get("keycloak_subject"): payload["id"] = spec["keycloak_subject"]
            user_id = kc.create_user(payload, exist_ok=True)
        kc.set_user_password(user_id, PASSWORD, temporary=False)
        out[username] = user_id
    return out

def seed_database(subjects: dict[str, str]) -> None:
    with get_db() as db:
        print("[db] cleaning up and seeding infrastructure...")
        db.execute(text("TRUNCATE notifications, custom_dashboards, dashboard_widgets, system_settings, metadata_key_definitions, ticket_metadatas, ticket_comments, ticket_status_history, ticket_sector_history, ticket_assignment_history, tickets, beneficiaries, sector_memberships, sectors, users CASCADE"))
        
        # 1. Dashboard Catalogue & Settings
        dashboard_service.sync_widget_catalogue(db)
        db.add(SystemSetting(key="autopilot_max_widgets", value=20))
        db.add(SystemSetting(key="autopilot_max_ticket_watchers", value=5))
        db.add(MetadataKeyDefinition(key="environment", label="Environment", value_type="enum", options=["prod", "stage", "dev"]))

        # 2. Infrastructure
        sectors = [Sector(code=c, name=n, description=f"Seeded {n}", is_active=True) for c, n in SECTORS]
        db.add_all(sectors)
        db.flush()
        
        users = []
        for spec in USERS:
            u = User(keycloak_subject=subjects[spec["username"]], username=spec["username"], email=spec["email"], first_name=spec["first_name"], last_name=spec["last_name"], user_type=spec["type"], is_active=True)
            db.add(u)
            users.append(u)
        db.flush()
        
        beneficiaries = [Beneficiary(user_id=u.id, beneficiary_type=u.user_type, first_name=u.first_name, last_name=u.last_name, email=u.email) for u in users]
        db.add_all(beneficiaries)
        db.flush()

        # Memberships
        for u in users:
            if u.username == "chief.s10": db.add(SectorMembership(user_id=u.id, sector_id=sectors[5].id, membership_role="chief", is_active=True))
            if u.username in ["member.s10", "chief.s10"]: db.add(SectorMembership(user_id=u.id, sector_id=sectors[5].id, membership_role="member", is_active=True))
            if u.username == "member.s2": db.add(SectorMembership(user_id=u.id, sector_id=sectors[1].id, membership_role="member", is_active=True))
        
        # 3. Tickets (1000 high-fidelity tickets)
        print("[db] seeding 1,000 high-fidelity tickets with history and conversations...")
        now = datetime.now(timezone.utc)
        internal_users = [u for u in users if u.user_type == "internal"]
        
        for i in range(1, 1001):
            created_at = now - timedelta(days=random.randint(0, 90), hours=random.randint(0, 23))
            status = random.choice(list(ALL_STATUSES))
            ben = random.choice(beneficiaries)
            
            t = Ticket(
                ticket_code=f"TK-{i:06d}", title=fake.sentence(nb_words=6), txt=fake.paragraph(nb_sentences=3),
                status=status, priority=random.choice(["low", "medium", "high", "critical"]),
                category=random.choice(["network", "hardware", "software", "access", "other"]),
                beneficiary_id=ben.id, beneficiary_type=ben.beneficiary_type,
                created_at=created_at, updated_at=created_at, reopened_count=0
            )
            db.add(t)
            db.flush()

            # Sequence of life
            # Start: Pending
            db.add(TicketStatusHistory(ticket_id=t.id, old_status=None, new_status="pending", created_at=created_at))
            
            curr_time = created_at + timedelta(minutes=random.randint(5, 120))
            if status != "pending":
                # Route to sector
                sec = random.choice(sectors)
                t.current_sector_id = sec.id
                db.add(TicketSectorHistory(ticket_id=t.id, old_sector_id=None, new_sector_id=sec.id, created_at=curr_time))
                if status != "assigned_to_sector":
                    # Assign to user
                    assignee = random.choice(internal_users)
                    t.assignee_user_id = assignee.id
                    db.add(TicketAssignmentHistory(ticket_id=t.id, old_assignee_id=None, new_assignee_id=assignee.id, created_at=curr_time + timedelta(minutes=10)))
                    db.add(TicketStatusHistory(ticket_id=t.id, old_status="pending", new_status="in_progress", created_at=curr_time + timedelta(minutes=15)))
            
            # Conversations
            num_comments = random.randint(0, 8)
            for j in range(num_comments):
                author = random.choice(users)
                db.add(TicketComment(ticket_id=t.id, author_user_id=author.id, body=fake.sentence(), visibility="public", created_at=curr_time + timedelta(hours=j+1)))
            
            # Resolution
            if status in DONE_STATUSES:
                res_time = curr_time + timedelta(days=random.randint(1, 5))
                t.done_at = res_time
                t.updated_at = res_time
                db.add(TicketStatusHistory(ticket_id=t.id, old_status="in_progress", new_status="done", created_at=res_time))
            
            # Notifications for some users
            if i % 10 == 0:
                db.add(Notification(user_id=random.choice(users).id, type="ticket_created", title="Ticket assigned", body=f"You have a new ticket: {t.ticket_code}", ticket_id=t.id))

        # 4. Global Dashboards
        for u in users:
            d = CustomDashboard(owner_user_id=u.id, title="My Operations", description="Auto-generated operations dashboard")
            db.add(d)
            db.flush()
            db.add(DashboardWidget(dashboard_id=d.id, type="welcome_banner", x=0, y=0, w=4, h=3))
            db.add(DashboardWidget(dashboard_id=d.id, type="ticket_list", x=4, y=0, w=8, h=6, config={"status": "in_progress"}))

        db.commit()
        print("[db] full dev mock system seeded successfully")

def main() -> int:
    subjects = seed_keycloak()
    seed_database(subjects)
    print("done.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
