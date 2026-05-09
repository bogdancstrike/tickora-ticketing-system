# Design Spec: Monitor & Auto-Pilot Refinements

**Status:** Draft
**Date:** 2026-05-10
**Author:** Gemini CLI

## 1. Overview
This project addresses bugs in the Monitor KPIs, improves the responsiveness of the trend charts, and adds deeper administrative control over the dashboard auto-configuration feature. It also introduces specialized views for Distributors.

## 2. Goals
- Fix the "Closed Today" counter to include `done` tickets.
- Enable smooth, non-refreshing updates for the Monitor trend chart.
- Implement "Not Yet Reviewed" and "Already Reviewed" widgets for Distributors.
- Extend Auto-Configure logic to add up to 5 specific ticket watchers.
- Add Admin-configurable limits for the Auto-Pilot engine.

## 3. Architecture & Data Flow

### 3.1 Backend: Monitor Fixes (`monitor_service.py`)
- **KPI Adjustment**: Update `_global_kpis` and `_sector_kpis` to use `func.coalesce(Ticket.done_at, Ticket.closed_at)` for the "finished today" metric.
- **Distributor Extension**: Add `_reviewed_today` query to `monitor_distributor` to track tickets transitioned from `pending` within the last 24h.

### 3.2 Backend: Auto-Pilot Settings (`models.py` & `dashboard_service.py`)
- **Settings Store**: Use the existing `WidgetDefinition` or a new `SystemSetting` table to store:
  - `autopilot_max_widgets`: (Default: 20)
  - `autopilot_max_ticket_watchers`: (Default: 5)
- **Heuristic Update**: `auto_configure_dashboard` will now:
  - Check `Principal`'s active tickets.
  - Generate a `recent_comments` widget for each (up to limit).
  - Respect the global limits set in Admin.

### 3.3 Frontend: UX Improvements (`MonitorPage.tsx` & `DashboardPage.tsx`)
- **Dynamic Refresh**: Update `useQuery` in `MonitorPage` to use `placeholderData: (previousData) => previousData`. This ensures the UI doesn't flicker when changing the time window.
- **Distributor Widgets**: 
  - `NotReviewedWidget`: Filtered list of `pending` tickets.
  - `AlreadyReviewedWidget`: Filtered list of tickets recently updated by distributors.

## 4. Implementation Plan
1. Fix backend KPI logic and distributor data.
2. Update frontend `MonitorPage` for smooth chart transitions.
3. Implement Distributor widgets in the frontend.
4. Add Auto-Pilot configuration table and Admin UI.
5. Enhance heuristic builder with dynamic ticket watchers.
