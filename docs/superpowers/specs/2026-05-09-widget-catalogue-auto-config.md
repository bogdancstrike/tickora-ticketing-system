# Design Spec: Widget Catalogue & Auto-Configure

**Status:** Draft
**Date:** 2026-05-09
**Author:** Gemini CLI

## 1. Overview
This project introduces a centralized **Widget Catalogue** for administrators to manage the naming and availability of dashboard widgets, and an **Auto-Configure** feature that automatically populates a user's dashboard with role-appropriate widgets and configurations.

## 2. Goals
- Provide Admin CRUD for widget display names, descriptions, and active status.
- Implement a heuristic engine to "auto-pilot" dashboard setup based on RBAC.
- Ensure safety with "Append" vs "Replace" modes for auto-configuration.
- Decouple widget metadata from the frontend hardcoded list.

## 3. Architecture & Data Flow

### 3.1 Backend: Data Model (`models.py`)
- **`WidgetDefinition`**:
  - `type` (PK): Unique string matching frontend component keys.
  - `display_name`: Admin-defined label.
  - `description`: Admin-defined tooltip/help text.
  - `is_active`: Global toggle for enabling/disabling the widget.
  - `icon`: Ant Design icon identifier.
  - `required_roles`: JSON list of roles permitted to manually add this widget.

### 3.2 Backend: Service Layer (`dashboard_service.py`)
- **`sync_widget_catalogue()`**: Internal utility to seed the DB with existing hardcoded types.
- **`auto_configure_dashboard(dashboard_id, mode, primary_sector)`**:
  - Validates ownership.
  - If `mode == 'replace'`, deletes existing `DashboardWidget` entries.
  - Computes a list of widgets based on `principal` roles:
    - **Admins:** `system_health`, `sla_overview`, `system_velocity`, `stale_tickets` (global), `audit_stream`, `bottleneck_analysis` (global).
    - **Chiefs:** `workload_balancer`, `bottleneck_analysis` (sector), `ticket_list` (sector), `stale_tickets` (sector).
    - **Members:** `ticket_list` (personal active), `recent_comments`, `monitor_kpi` (personal), `stale_tickets` (personal).
    - **Beneficiaries:** `ticket_list` (my requests), `recent_comments` (public), `shortcuts`, `profile_card`.
  - Calculates a non-overlapping grid layout for the generated widgets.

### 3.3 Frontend: Integration
- **`AdminPage`**: New "Widget Catalogue" tab in Configuration.
- **`DashboardPage`**:
  - "Auto-configure" button in the toolbar.
  - Choice Modal: "Append Recommended" vs "Replace with Recommended".
  - Replace the hardcoded `WIDGET_TYPES` with a query to the backend catalogue.

## 4. Security & RBAC
- **Catalogue Management:** Restricted to `tickora_admin`.
- **Auto-Configure:** respects existing `_check_not_beneficiary` rules (unless we explicitly want to allow beneficiaries to have dashboards now). *Correction:* Per requirements, beneficiaries can have dashboards, so `_check_not_beneficiary` will be relaxed to allow basic self-service dashboards.

## 5. Implementation Plan (Next Steps)
1. Migration for `widget_definitions` table.
2. Backend CRUD and seeding logic in `dashboard_service.py`.
3. Heuristic builder logic for auto-configuration.
4. Admin UI for managing the catalogue.
5. Dashboard UI for the "Magic Wand" auto-config button.
