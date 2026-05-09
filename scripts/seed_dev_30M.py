#!/usr/bin/env python3
"""Seed local development data with 30 Million tickets for load testing.

WARNING: This will take a significant amount of time and storage.
Ensure your Postgres instance is tuned and has enough disk space.
To stop the script, press Ctrl+C.
"""
import sys
import time
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import insert, select
from src.core.db import get_db
from src.iam.models import User
from src.ticketing.models import Beneficiary, Sector, Ticket, TicketStatusHistory
from src.ticketing.state_machine import ALL_STATUSES

BATCH_SIZE = 50000
TOTAL_TICKETS = 30_000_000

def generate_and_insert(db, start_idx, count, users, sectors, beneficiaries, categories, priorities, all_st):
    now = datetime.now(timezone.utc)
    tickets = []
    histories = []
    
    internal_users = [u for u in users if u["type"] == "internal"]
    if not internal_users:
        internal_users = users
        
    for i in range(count):
        idx = start_idx + i
        created_at = now - timedelta(days=random.randint(0, 365), hours=random.randint(0, 23))
        status = random.choice(all_st)
        priority = random.choice(priorities)
        ben = random.choice(beneficiaries)
        creator = random.choice(internal_users) if ben["type"] == "internal" else None
        
        sector_id = random.choice(sectors)["id"] if status != "pending" else None
        assignee = random.choice(internal_users) if status in ["in_progress", "done", "closed"] else None
        
        finished_at = None
        if status in ["done", "closed"]:
            finished_at = created_at + timedelta(hours=random.randint(1, 48))
            
        ticket_id = str(uuid.uuid4())
        
        tickets.append({
            "id": ticket_id,
            "ticket_code": f"TK-30M-{idx:08d}",
            "title": f"Load Test Ticket {idx}",
            "txt": "Generated automatically for extreme load testing of the ticketing platform.",
            "status": status,
            "priority": priority,
            "category": random.choice(categories),
            "beneficiary_id": ben["id"],
            "beneficiary_type": ben["type"],
            "created_by_user_id": creator["id"] if creator else None,
            "current_sector_id": sector_id,
            "assignee_user_id": assignee["id"] if assignee else None,
            "created_at": created_at,
            "updated_at": finished_at or created_at,
            "done_at": finished_at if status == "done" else None,
            "closed_at": finished_at if status == "closed" else None,
            "requester_email": ben["email"],
            "requester_first_name": ben["first_name"],
            "requester_last_name": ben["last_name"],
            "is_deleted": False,
            "reopened_count": 0,
        })
        
        histories.append({
            "id": str(uuid.uuid4()),
            "ticket_id": ticket_id,
            "old_status": None,
            "new_status": "pending",
            "created_at": created_at,
        })
        if status != "pending":
            histories.append({
                "id": str(uuid.uuid4()),
                "ticket_id": ticket_id,
                "old_status": "pending",
                "new_status": status,
                "created_at": created_at + timedelta(minutes=random.randint(5, 60))
            })

    db.execute(insert(Ticket), tickets)
    db.execute(insert(TicketStatusHistory), histories)
    db.commit()

def main() -> int:
    print(f"Preparing to seed {TOTAL_TICKETS:,} tickets...")
    with get_db() as db:
        users = [{"id": u.id, "type": u.user_type} for u in db.scalars(select(User)).all()]
        sectors = [{"id": s.id} for s in db.scalars(select(Sector)).all()]
        beneficiaries = [{"id": b.id, "type": b.beneficiary_type, "email": b.email, "first_name": b.first_name, "last_name": b.last_name} for b in db.scalars(select(Beneficiary)).all()]
        
        if not users or not sectors or not beneficiaries:
            print("Error: Missing base data. Please run seed_dev.py first to create base users and sectors.")
            return 1
            
        all_st = list(ALL_STATUSES)
        priorities = ["low", "medium", "high", "critical"]
        categories = ["network", "hardware", "software", "access", "other"]

        start_time = time.time()
        
        for batch_start in range(0, TOTAL_TICKETS, BATCH_SIZE):
            try:
                generate_and_insert(
                    db, 
                    batch_start, 
                    BATCH_SIZE, 
                    users, sectors, beneficiaries, categories, priorities, all_st
                )
                
                elapsed = time.time() - start_time
                rate = (batch_start + BATCH_SIZE) / elapsed
                print(f"Inserted {batch_start + BATCH_SIZE:,} / {TOTAL_TICKETS:,} ({rate:,.0f} tkts/sec)")
            except KeyboardInterrupt:
                print("\nInterrupted by user. Stopping seed.")
                break
            except Exception as e:
                print(f"\nError during batch insert: {e}")
                db.rollback()
                break

    print(f"Done in {time.time() - start_time:.2f}s")
    return 0

if __name__ == "__main__":
    sys.exit(main())
