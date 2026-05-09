# Monitor & Auto-Pilot Refinements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix Monitor "Closed Today" bug, enable smooth chart transitions, implement Distributor widgets, and add Admin-configurable Auto-Pilot limits.

**Architecture:** 
1. Update `monitor_service.py` with improved KPI and Distributor queries.
2. Refactor `MonitorPage.tsx` for placeholder data.
3. Create `SystemSetting` model for global Auto-Pilot configuration.
4. Enhance `auto_configure_dashboard` logic with dynamic watcher limits.

**Tech Stack:** Python (SQLAlchemy), React (TanStack Query, ECharts).

---

### Task 1: Backend - Monitor & Distributor Fixes

**Files:**
- Modify: `src/ticketing/service/monitor_service.py`
- Test: `tests/integration/test_monitor_service_refinements.py`

- [ ] **Step 1: Fix `closed_today` KPI logic**
Update `_global_kpis` to use `func.coalesce(Ticket.done_at, Ticket.closed_at)` for today's comparison.

- [ ] **Step 2: Add `_reviewed_today` to `monitor_distributor`**
Implement query to find tickets that were moved out of `pending` by a distributor within the last 24h.

- [ ] **Step 3: Commit**

---

### Task 2: Frontend - Smooth Chart Transitions

**Files:**
- Modify: `frontend/src/pages/MonitorPage.tsx`

- [ ] **Step 1: Add `placeholderData` to `useQuery`**
```typescript
const overview = useQuery({
  queryKey: ['monitorOverview', days],
  queryFn: () => getMonitorOverview(days),
  placeholderData: (prev) => prev, // Keeps chart visible while loading new window
  staleTime: 60_000,
})
```

---

### Task 3: Backend - Auto-Pilot Settings Model

**Files:**
- Modify: `src/ticketing/models.py`
- Create: `migrations/versions/XXXX_add_system_settings.py`

- [ ] **Step 1: Add `SystemSetting` model**
Simple key-value table: `key` (PK), `value` (JSONB), `description`.

- [ ] **Step 2: Create and run migration**

---

### Task 4: Backend - Enhanced Heuristics

**Files:**
- Modify: `src/ticketing/service/dashboard_service.py`

- [ ] **Step 1: Load settings in `auto_configure_dashboard`**
Fetch `autopilot_max_ticket_watchers` from the new settings table.

- [ ] **Step 2: Update dynamic watcher logic**
Ensure up to the limit (default 5) most recent tickets are added.

---

### Task 5: Frontend - Admin & Distributor UI

**Files:**
- Modify: `frontend/src/pages/AdminPage.tsx`
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Add "Auto-Pilot Settings" panel to Admin**
- [ ] **Step 2: Implement "Not Yet Reviewed" and "Already Reviewed" list widgets**
- [ ] **Step 3: Update `WidgetRenderer` in `DashboardPage.tsx`**
