#!/usr/bin/env python3
"""Seed local development data with 30 Million tickets for load testing.

Optimized version: generates history, conversations, and notifications in bulk.
"""
import sys
import time
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import insert, select, text
from src.core.db import get_db
from src.iam.models import User
from src.ticketing.models import (
    Beneficiary, Sector, Ticket, TicketStatusHistory, 
    TicketComment, Notification, TicketSectorHistory, TicketAssignmentHistory
)
from src.ticketing.state_machine import ALL_STATUSES, DONE_STATUSES

BATCH_SIZE = 25000
TOTAL_TICKETS = 30_000_000

def generate_batch(start_idx, count, users, sectors, beneficiaries, all_st):
    now = datetime.now(timezone.utc)
    
    batch_tickets = []
    batch_histories = []
    batch_comments = []
    batch_notifications = []
    
    internal_users = [u for u in users if u["type"] == "internal"]
    if not internal_users: internal_users = users

    priorities = ["low", "medium", "high", "critical"]
    categories = ["network", "hardware", "software", "access", "other"]

    for i in range(count):
        idx = start_idx + i
        created_at = now - timedelta(days=random.randint(0, 365), hours=random.randint(0, 23))
        status = random.choice(all_st)
        ben = random.choice(beneficiaries)
        creator = random.choice(internal_users) if ben["type"] == "internal" else None
        
        ticket_id = str(uuid.uuid4())
        sector = random.choice(sectors) if status != "pending" else None
        assignee = random.choice(internal_users) if status in ["in_progress", "done", "closed"] else None
        
        finished_at = None
        if status in DONE_STATUSES:
            finished_at = created_at + timedelta(hours=random.randint(1, 72))

        batch_tickets.append({
            "id": ticket_id, "ticket_code": f"TK-XP-{idx:08d}", "title": f"Load test ticket {idx}",
            "txt": "Extreme scale data point for performance verification.", "status": status,
            "priority": random.choice(priorities), "category": random.choice(categories),
            "beneficiary_id": ben["id"], "beneficiary_type": ben["type"],
            "created_by_user_id": creator["id"] if creator else None,
            "current_sector_id": sector["id"] if sector else None,
            "assignee_user_id": assignee["id"] if assignee else None,
            "created_at": created_at, "updated_at": finished_at or created_at,
            "done_at": finished_at if status == "done" else None,
            "closed_at": finished_at if status == "closed" else None,
            "requester_email": ben["email"], "requester_first_name": ben["first_name"], "requester_last_name": ben["last_name"],
            "is_deleted": False, "reopened_count": 0
        })

        # History: Base pending
        batch_histories.append({
            "id": str(uuid.uuid4()), "ticket_id": ticket_id, "old_status": None, "new_status": "pending", "created_at": created_at
        })
        
        if status != "pending":
            # Simulation of triage
            triage_at = created_at + timedelta(minutes=random.randint(10, 60))
            if status != "assigned_to_sector":
                batch_histories.append({
                    "id": str(uuid.uuid4()), "ticket_id": ticket_id, "old_status": "pending", "new_status": "in_progress", "created_at": triage_at
                })
            
            # Resolution history
            if finished_at:
                batch_histories.append({
                    "id": str(uuid.uuid4()), "ticket_id": ticket_id, "old_status": "in_progress", "new_status": status, "created_at": finished_at
                })

        # Random Conversation (10% of tickets have conversations)
        if random.random() < 0.1:
            for j in range(random.randint(1, 3)):
                batch_comments.append({
                    "id": str(uuid.uuid4()), "ticket_id": ticket_id, "author_user_id": random.choice(users)["id"],
                    "body": f"Scaling test response {j}", "visibility": "public", "comment_type": "user_comment",
                    "created_at": created_at + timedelta(hours=j+1)
                })

        # Random Notification (1% of tickets)
        if random.random() < 0.01:
            batch_notifications.append({
                "id": str(uuid.uuid4()), "user_id": random.choice(users)["id"], "type": "ticket_created",
                "title": "Scalability Alert", "body": f"Massive data ingest ticket: TK-XP-{idx:08d}",
                "ticket_id": ticket_id, "read": False, "created_at": now
            })

    return batch_tickets, batch_histories, batch_comments, batch_notifications

def main() -> int:
    print(f"Starting optimized massive seed: {TOTAL_TICKETS:,} tickets...")
    with get_db() as db:
        users = [{"id": u.id, "type": u.user_type} for u in db.scalars(select(User)).all()]
        sectors = [{"id": s.id} for s in db.scalars(select(Sector)).all()]
        beneficiaries = [{"id": b.id, "type": b.beneficiary_type, "email": b.email, "first_name": b.first_name, "last_name": b.last_name} for b in db.scalars(select(Beneficiary)).all()]
        
        if not users or not beneficiaries:
            print("Run seed_dev.py first.")
            return 1
            
        all_st = list(ALL_STATUSES)
        start_time = time.time()
        
        for batch_start in range(0, TOTAL_TICKETS, BATCH_SIZE):
            try:
                tkts, hist, comms, notifs = generate_batch(batch_start, BATCH_SIZE, users, sectors, beneficiaries, all_st)
                
                db.execute(insert(Ticket), tkts)
                db.execute(insert(TicketStatusHistory), hist)
                if comms: db.execute(insert(TicketComment), comms)
                if notifs: db.execute(insert(Notification), notifs)
                
                db.commit()
                
                elapsed = time.time() - start_time
                rate = (batch_start + BATCH_SIZE) / elapsed
                print(f"Progress: {batch_start + BATCH_SIZE:,} / {TOTAL_TICKETS:,} ({rate:,.0f} tickets/sec)")
            except KeyboardInterrupt:
                print("\nStopped.")
                break
            except Exception as e:
                print(f"Error: {e}")
                db.rollback()
                break

    return 0

if __name__ == "__main__":
    sys.exit(main())
