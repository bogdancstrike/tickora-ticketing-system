# Dashboard & Monitor Extensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Stale Ticket detection, Workload Balancing, Bottleneck Analysis, and System Velocity trends across the dashboard and monitor pages.

**Architecture:** Extend `monitor_service.py` with new aggregation functions (stale detection via comment subqueries, bottleneck analysis via history aggregation). Refactor frontend charts into reusable components and add new widget types to `DashboardPage.tsx`.

**Tech Stack:** Python (Flask/SQLAlchemy), React (TypeScript/Ant Design/ECharts).

---

### Task 1: Backend - Stale Ticket Metrics

**Files:**
- Modify: `src/ticketing/service/monitor_service.py`
- Test: `tests/integration/test_monitor_service.py`

- [ ] **Step 1: Write integration test for stale tickets**

```python
def test_stale_tickets_detection(db, principal):
    # Create an active ticket with no comments
    t1 = create_test_ticket(db, status="in_progress", created_at=now - 48h)
    # Create an active ticket with a recent comment
    t2 = create_test_ticket(db, status="in_progress", created_at=now - 48h)
    add_comment(db, t2.id, created_at=now - 1h)
    
    stale = monitor_service._stale_tickets(db, principal, hours=24)
    assert len(stale) == 1
    assert stale[0]["id"] == t1.id
```

- [ ] **Step 2: Implement `_stale_tickets` in `monitor_service.py`**

```python
def _stale_tickets(db: Session, principal: Principal, hours: int = 24, limit: int = 10) -> list[dict[str, Any]]:
    from src.ticketing.models import TicketComment
    threshold = datetime.now(timezone.utc) - timedelta(hours=hours)
    
    # Tickets with NO comments since threshold
    last_comment_sub = (
        select(TicketComment.ticket_id, func.max(TicketComment.created_at).label("last_activity"))
        .group_by(TicketComment.ticket_id)
        .subquery()
    )
    
    stmt = _visible_stmt(principal).where(Ticket.status.in_(ACTIVE_STATUSES))
    stmt = stmt.outerjoin(last_comment_sub, last_comment_sub.c.ticket_id == Ticket.id)
    stmt = stmt.where(
        or_(
            last_comment_sub.c.last_activity.is_(None),
            last_comment_sub.c.last_activity < threshold
        )
    )
    
    rows = db.execute(stmt.order_by(Ticket.created_at.asc()).limit(limit)).scalars().all()
    return [{
        "id": t.id,
        "ticket_code": t.ticket_code,
        "title": t.title,
        "status": t.status,
        "created_at": t.created_at.isoformat(),
        "last_activity": None # logic for display
    } for t in rows]
```

- [ ] **Step 3: Run tests and commit**

---

### Task 2: Backend - Bottleneck Analysis

**Files:**
- Modify: `src/ticketing/service/monitor_service.py`
- Test: `tests/integration/test_monitor_service.py`

- [ ] **Step 1: Implement `_bottleneck_analysis`**

```python
def _bottleneck_analysis(db: Session, sector_id: str | None = None, days: int = 30) -> list[dict[str, Any]]:
    from src.ticketing.models import TicketStatusHistory
    # Calculate average time spent in each status for tickets closed in last X days
    stmt = (
        select(TicketStatusHistory.new_status, func.avg(Ticket.closed_at - TicketStatusHistory.created_at))
        .join(Ticket, Ticket.id == TicketStatusHistory.ticket_id)
        .where(Ticket.status == 'closed', Ticket.closed_at >= datetime.now(timezone.utc) - timedelta(days=days))
    )
    if sector_id:
        stmt = stmt.where(Ticket.current_sector_id == sector_id)
    # Group and aggregate logic...
    return [] # implementation details
```

- [ ] **Step 2: Run tests and commit**

---

### Task 3: Frontend - Reusable Chart Components

**Files:**
- Modify: `frontend/src/pages/MonitorPage.tsx`
- Create: `frontend/src/components/dashboard/charts.tsx` (optional refactor)

- [ ] **Step 1: Refactor `BreakdownChart` and `DoughnutChart` for reusability**
- [ ] **Step 2: Add `ThroughputChart` (Horizontal Bar for Workload)**

---

### Task 4: Frontend - Dashboard Widget Implementation

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Add new types to `WIDGET_TYPES`**
- [ ] **Step 2: Implement `StaleTicketsWidget` component**
- [ ] **Step 3: Implement `WorkloadBalancerWidget` component**
- [ ] **Step 4: Implement `BottleneckWidget` component**

---

### Task 5: Frontend - Monitor Page Integration

**Files:**
- Modify: `frontend/src/pages/MonitorPage.tsx`

- [ ] **Step 1: Update Sector tab to include Bottleneck chart**
- [ ] **Step 2: Update Global tab to include System Velocity at the top**
- [ ] **Step 3: Verify overall layout and data loading**
