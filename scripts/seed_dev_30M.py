#!/usr/bin/env python3
"""Bulk-insert N tickets for load + perf testing.

Designed to run **after** `seed_dev.py` — it requires existing users,
sectors, and beneficiaries because every generated ticket has FKs
pointing at them.

Idempotent: re-running appends more tickets (codes are
`TK-XP-<offset+i>` so collisions only happen if you run twice with the
same offset). Stop any time with Ctrl-C — already-committed batches
stay.

Tunables via env:
  * `SEED_30M_TOTAL`   — total tickets to generate (default 30_000_000).
  * `SEED_30M_BATCH`   — rows per commit (default 25_000).
  * `SEED_30M_OFFSET`  — where to start the `TK-XP-<n>` sequence
                          (default: continues from the highest existing
                          `TK-XP-` code).
  * `SEED_30M_RUN_MIGRATIONS` — `1` (default) to ensure the schema is
                          up to date before seeding.

Performance notes:
  * Uses `executemany` via `db.execute(insert(Model), rows)` — much
    cheaper than ORM `add` per row.
  * Skips status_history / sector_history beyond the canonical "pending"
    + transition rows, so we hit roughly 50k rows/sec on a developer
    laptop.
  * Tickets only carry minimal payload; for FTS or detail-page perf
    tests prefer the regular `seed_dev.py` and bump `SEED_TICKETS`.
"""
from __future__ import annotations

import os
import random
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import insert, inspect, select

from src.core.db import get_db, get_engine
from src.iam.models import User
from src.ticketing.models import (
    Beneficiary,
    Notification,
    Sector,
    Ticket,
    TicketComment,
    TicketStatusHistory,
)
from src.ticketing.state_machine import ALL_STATUSES, DONE_STATUSES


def _tables_exist() -> bool:
    try:
        return inspect(get_engine()).has_table("tickets")
    except Exception:
        return False


def run_migrations_if_needed() -> None:
    if os.getenv("SEED_30M_RUN_MIGRATIONS", "1") not in ("1", "true", "True"):
        return
    if not _tables_exist():
        print("[migrate] empty schema — running `alembic upgrade head`…")
        res = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(ROOT), check=False,
        )
        if res.returncode != 0:
            raise SystemExit(f"alembic upgrade failed (exit {res.returncode})")


def _next_xp_offset(db) -> int:
    """Find the highest existing `TK-XP-<n>` so re-runs don't collide.

    We pull the max ticket_code that starts with `TK-XP-`, parse the
    numeric tail, and start the next batch at `n+1`.
    """
    code = db.scalar(
        select(Ticket.ticket_code)
        .where(Ticket.ticket_code.like("TK-XP-%"))
        .order_by(Ticket.ticket_code.desc())
        .limit(1)
    )
    if not code:
        return 0
    try:
        return int(code.removeprefix("TK-XP-")) + 1
    except ValueError:
        return 0


def generate_batch(start_idx, count, users, sectors, beneficiaries, all_statuses):
    """Build a list of dicts ready for `db.execute(insert(Ticket), rows)`."""
    now = datetime.now(timezone.utc)
    batch_tickets:       list[dict] = []
    batch_histories:     list[dict] = []
    batch_comments:      list[dict] = []
    batch_notifications: list[dict] = []

    internal_users = [u for u in users if u["type"] == "internal"] or users
    priorities = ["low", "medium", "high", "critical"]
    categories = ["network", "hardware", "software", "access", "other"]

    for i in range(count):
        idx = start_idx + i
        created_at = now - timedelta(
            days=random.randint(0, 365),
            hours=random.randint(0, 23),
        )
        status = random.choice(all_statuses)
        ben = random.choice(beneficiaries)
        creator = random.choice(internal_users) if ben["type"] == "internal" else None

        ticket_id = str(uuid.uuid4())
        sector = random.choice(sectors) if (sectors and status != "pending") else None
        assignee = random.choice(internal_users) if status in ("in_progress", "done") else None

        finished_at = (
            created_at + timedelta(hours=random.randint(1, 72))
            if status in DONE_STATUSES else None
        )

        batch_tickets.append({
            "id": ticket_id,
            "ticket_code": f"TK-XP-{idx:08d}",
            "title": f"Load test ticket {idx}",
            "txt": "Extreme scale data point for performance verification.",
            "status": status,
            "priority": random.choice(priorities),
            "category": random.choice(categories),
            "beneficiary_id": ben["id"],
            "beneficiary_type": ben["type"],
            "created_by_user_id": creator["id"] if creator else None,
            "current_sector_id": sector["id"] if sector else None,
            "assignee_user_id": assignee["id"] if assignee else None,
            "created_at": created_at,
            "updated_at": finished_at or created_at,
            "done_at":   finished_at if status == "done"   else None,
            "closed_at": None,
            "requester_email":      ben["email"],
            "requester_first_name": ben["first_name"],
            "requester_last_name":  ben["last_name"],
            "is_deleted": False,
            "reopened_count": 0,
        })

        batch_histories.append({
            "id": str(uuid.uuid4()),
            "ticket_id": ticket_id,
            "old_status": None,
            "new_status": "pending",
            "created_at": created_at,
        })

        if status != "pending":
            triage_at = created_at + timedelta(minutes=random.randint(10, 60))
            if status != "assigned_to_sector":
                batch_histories.append({
                    "id": str(uuid.uuid4()),
                    "ticket_id": ticket_id,
                    "old_status": "pending",
                    "new_status": "in_progress",
                    "created_at": triage_at,
                })
            if finished_at:
                batch_histories.append({
                    "id": str(uuid.uuid4()),
                    "ticket_id": ticket_id,
                    "old_status": "in_progress",
                    "new_status": status,
                    "created_at": finished_at,
                })

        if random.random() < 0.1:
            for j in range(random.randint(1, 3)):
                batch_comments.append({
                    "id": str(uuid.uuid4()),
                    "ticket_id": ticket_id,
                    "author_user_id": random.choice(users)["id"],
                    "body": f"Scaling test response {j}",
                    "visibility": "public",
                    "comment_type": "user_comment",
                    "created_at": created_at + timedelta(hours=j + 1),
                })

        if random.random() < 0.01:
            batch_notifications.append({
                "id": str(uuid.uuid4()),
                "user_id": random.choice(users)["id"],
                "type": "ticket_created",
                "title": "Scalability Alert",
                "body":  f"Massive data ingest ticket: TK-XP-{idx:08d}",
                "ticket_id": ticket_id,
                "is_read": False,
                "created_at": now,
            })

    return batch_tickets, batch_histories, batch_comments, batch_notifications


def main() -> int:
    run_migrations_if_needed()

    total       = int(os.getenv("SEED_30M_TOTAL",  "30000000"))
    batch_size  = int(os.getenv("SEED_30M_BATCH",  "25000"))
    explicit_offset = os.getenv("SEED_30M_OFFSET")

    print(f"Bulk seed: target={total:,} tickets · batch={batch_size:,}")
    with get_db() as db:
        users = [{"id": u.id, "type": u.user_type} for u in db.scalars(select(User)).all()]
        sectors = [{"id": s.id} for s in db.scalars(select(Sector)).all()]
        beneficiaries = [
            {"id": b.id, "type": b.beneficiary_type, "email": b.email,
             "first_name": b.first_name, "last_name": b.last_name}
            for b in db.scalars(select(Beneficiary)).all()
        ]

        if not users or not beneficiaries:
            print(
                "[seed_dev_30M] no users / beneficiaries present — run "
                "`scripts/seed_dev.py` first.",
                file=sys.stderr,
            )
            return 1

        offset = int(explicit_offset) if explicit_offset is not None else _next_xp_offset(db)
        if offset:
            print(f"[seed_dev_30M] resuming from offset {offset:,}")

        all_statuses = list(ALL_STATUSES)
        start_time = time.time()

        produced = 0
        try:
            for batch_start in range(offset, offset + total, batch_size):
                tkts, hist, comms, notifs = generate_batch(
                    batch_start, batch_size, users, sectors, beneficiaries, all_statuses,
                )
                db.execute(insert(Ticket),               tkts)
                db.execute(insert(TicketStatusHistory),  hist)
                if comms:
                    db.execute(insert(TicketComment),    comms)
                if notifs:
                    db.execute(insert(Notification),     notifs)
                db.commit()
                produced += batch_size

                elapsed = time.time() - start_time
                rate = produced / elapsed if elapsed > 0 else 0.0
                print(f"  progress: {produced:,} / {total:,} ({rate:,.0f} tickets/sec)")
        except KeyboardInterrupt:
            print("\nstopped — already-committed batches preserved.")
        except Exception as exc:
            db.rollback()
            print(f"[seed_dev_30M] error: {exc}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
