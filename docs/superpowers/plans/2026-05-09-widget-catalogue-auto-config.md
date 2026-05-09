# Widget Catalogue & Auto-Configure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a centralized Widget Catalogue for Admins and a role-based Auto-Configure feature for user dashboards.

**Architecture:** 
1. New `WidgetDefinition` model for the catalogue.
2. Extended `dashboard_service.py` with heuristic builder for auto-configuration.
3. New API endpoints in `admin.py` (catalogue CRUD) and `dashboard.py` (auto-configure).
4. Frontend Admin UI for catalogue management.
5. Frontend Dashboard UI for "Auto-configure" with safety modes.

**Tech Stack:** Python (Flask/SQLAlchemy), React (TypeScript/Ant Design).

---

### Task 1: Backend - Database Migration & Models

**Files:**
- Modify: `src/ticketing/models.py`
- Create: `migrations/versions/XXXX_add_widget_catalogue.py`

- [ ] **Step 1: Add `WidgetDefinition` model**
```python
class WidgetDefinition(Base):
    __tablename__ = "widget_definitions"

    type:         Mapped[str]  = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str]  = mapped_column(String(255), nullable=False)
    description:  Mapped[str | None] = mapped_column(Text)
    is_active:    Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    icon:         Mapped[str | None] = mapped_column(String(50))
    required_roles: Mapped[list[str] | None] = mapped_column(JSONB)
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
```

- [ ] **Step 2: Create migration**
Run: `alembic revision -m "add widget catalogue"` and fill the script.

- [ ] **Step 3: Commit**
```bash
git add src/ticketing/models.py migrations/versions/*.py
git commit -m "feat: add WidgetDefinition model and migration"
```

---

### Task 2: Backend - Dashboard Service Extensions

**Files:**
- Modify: `src/ticketing/service/dashboard_service.py`
- Test: `tests/integration/test_dashboard_service_auto_config.py`

- [ ] **Step 1: Relax `_check_not_beneficiary` to allow basic dashboards**
```python
def _check_dashboard_access(p: Principal) -> None:
    # Allow everyone to have dashboards, but maybe restrict features later if needed.
    pass 
```

- [ ] **Step 2: Implement `sync_widget_catalogue`**
Seed the DB with current hardcoded types (`ticket_list`, `monitor_kpi`, etc.).

- [ ] **Step 3: Implement `auto_configure_dashboard` heuristic logic**
Compute role-appropriate widgets and grid positions.

- [ ] **Step 4: Write integration tests for heuristics**
Verify Admin gets global widgets and Beneficiary gets "My Requests".

- [ ] **Step 5: Commit**

---

### Task 3: Backend - API Endpoints

**Files:**
- Modify: `src/api/admin.py`
- Modify: `src/api/dashboard.py`
- Modify: `maps/endpoint.json`

- [ ] **Step 1: Add catalogue CRUD to `admin.py`**
- [ ] **Step 2: Add `auto_configure` to `dashboard.py`**
- [ ] **Step 3: Register endpoints in `endpoint.json`**
- [ ] **Step 4: Commit**

---

### Task 4: Frontend - API & Admin UI

**Files:**
- Modify: `frontend/src/api/tickets.ts`
- Modify: `frontend/src/api/admin.ts`
- Modify: `frontend/src/pages/AdminPage.tsx`

- [ ] **Step 1: Add API client functions**
- [ ] **Step 2: Implement "Widget Catalogue" tab in `AdminPage.tsx`**
Table with Edit modal (name, description, active toggle).

---

### Task 5: Frontend - Dashboard "Auto-Pilot" UI

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Replace hardcoded `WIDGET_TYPES` with backend fetch**
- [ ] **Step 2: Add "Auto-configure" button (Magic Wand icon)**
- [ ] **Step 3: Implement Choice Modal (Append vs Replace)**
- [ ] **Step 4: Final verification and smoke test**
