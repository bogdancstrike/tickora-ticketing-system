# Bottleneck Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement bottleneck analysis to calculate average time tickets spend in each status for recently closed tickets.

**Architecture:** Use a SQL aggregate query with window functions (or a correlated subquery if window functions are tricky in SQLAlchemy Core) to calculate durations from `TicketStatusHistory` and `Ticket.created_at`.

**Tech Stack:** Python, SQLAlchemy, PostgreSQL.

---

### Task 1: Research and Prep

- [ ] **Step 1: Verify database schema for History**
  Confirm `TicketStatusHistory` and `Ticket` columns.
- [ ] **Step 2: Check current monitor service structure**
  Identify where to insert `_bottleneck_analysis` and how to integrate with `monitor_global` and `monitor_sector`.

### Task 2: Implement Bottleneck Analysis Logic

**Files:**
- Modify: `src/ticketing/service/monitor_service.py`

- [ ] **Step 1: Implement `_bottleneck_analysis` helper**
  This function will perform the SQL aggregation.

```python
def _bottleneck_analysis(db: Session, sector_id: str | None = None, days: int = 30) -> list[dict[str, Any]]:
    from src.ticketing.models import TicketStatusHistory, Ticket
    
    threshold = datetime.now(timezone.utc) - timedelta(days=days)
    
    # We want to find durations of each status.
    # For a given history entry h, the duration of h.old_status is 
    # h.created_at - (previous h.created_at OR ticket.created_at).
    
    # Subquery to get history with previous timestamp
    # Using a subquery with LAG window function
    h = TicketStatusHistory.__table__.alias("h")
    t = Ticket.__table__.alias("t")
    
    prev_at = func.lag(h.c.created_at).over(partition_by=h.c.ticket_id, order_by=h.c.created_at)
    # If prev_at is null, it means it's the first transition, so use ticket.created_at
    started_at = func.coalesce(prev_at, t.c.created_at)
    duration_sec = func.extract("epoch", h.c.created_at - started_at)
    
    inner_stmt = (
        select(
            h.c.old_status.label("status"),
            duration_sec.label("duration")
        )
        .join(t, t.c.id == h.c.ticket_id)
        .where(t.c.status == "closed")
        .where(t.c.closed_at >= threshold)
        .where(t.c.is_deleted.is_(False))
    )
    
    if sector_id:
        inner_stmt = inner_stmt.where(t.c.current_sector_id == sector_id)
        
    subq = inner_stmt.subquery()
    
    stmt = (
        select(
            subq.c.status,
            func.avg(subq.c.duration).label("avg_duration_sec"),
            func.count().label("transition_count")
        )
        .group_by(subq.c.status)
        .order_by(func.avg(subq.c.duration).desc())
    )
    
    results = db.execute(stmt).all()
    
    return [
        {
            "status": row.status or "pending",
            "avg_minutes": round(float(row.avg_duration_sec) / 60, 1) if row.avg_duration_sec is not None else 0,
            "count": int(row.transition_count)
        }
        for row in results
    ]
```

- [ ] **Step 2: Expose in `monitor_global`**
- [ ] **Step 3: Expose in `monitor_sector`**

### Task 3: Integration Tests

**Files:**
- Create: `tests/integration/test_bottleneck_analysis.py`

- [ ] **Step 1: Write integration test**
  Setup a ticket, move it through statuses with explicit delays (using `freezegun` or manual `created_at` overrides if possible, but integration tests usually run against real DB. For real DB, we might need to manually insert history entries with old timestamps to avoid waiting).
  
```python
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from src.ticketing.models import Ticket, TicketStatusHistory
from src.ticketing.service.monitor_service import _bottleneck_analysis
from tests.integration.conftest import create_ticket, create_user, create_sector, create_beneficiary

def test_bottleneck_analysis_calculation(db_session: Session):
    # Setup
    sector = create_sector(db_session, "BN-TEST")
    user = create_user(db_session, "bn_analyst")
    beneficiary = create_beneficiary(db_session, user)
    
    # Create a ticket
    now = datetime.now(timezone.utc)
    t1 = create_ticket(db_session, beneficiary, created_by=user, current_sector=sector)
    t1.created_at = now - timedelta(hours=10)
    db_session.flush()
    
    # Add history manually to simulate time spent
    # pending for 2 hours
    h1 = TicketStatusHistory(
        ticket_id=t1.id, old_status="pending", new_status="assigned_to_sector",
        created_at=now - timedelta(hours=8)
    )
    # assigned_to_sector for 3 hours
    h2 = TicketStatusHistory(
        ticket_id=t1.id, old_status="assigned_to_sector", new_status="in_progress",
        created_at=now - timedelta(hours=5)
    )
    # in_progress for 4 hours
    h3 = TicketStatusHistory(
        ticket_id=t1.id, old_status="in_progress", new_status="closed",
        created_at=now - timedelta(hours=1)
    )
    db_session.add_all([h1, h2, h3])
    
    t1.status = "closed"
    t1.closed_at = now - timedelta(hours=1)
    db_session.commit()
    
    # Run analysis
    analysis = _bottleneck_analysis(db_session, days=1)
    
    # Verify
    # pending: 2h = 120m
    # assigned_to_sector: 3h = 180m
    # in_progress: 4h = 240m
    
    results = {r["status"]: r["avg_minutes"] for r in analysis}
    assert results["pending"] == 120.0
    assert results["assigned_to_sector"] == 180.0
    assert results["in_progress"] == 240.0
```

- [ ] **Step 2: Run and verify tests**
  Run: `pytest tests/integration/test_bottleneck_analysis.py`
