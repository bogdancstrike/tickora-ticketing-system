# Design Spec: Dashboard & Monitor Extensions

**Status:** Draft
**Date:** 2026-05-09
**Author:** Gemini CLI

## 1. Overview
This project extends the Tickora dashboard and monitor pages with advanced operational widgets: Stale Ticket detection, Workload Balancing, Bottleneck Analysis, and System Velocity trends. These tools provide managers and operators with deeper insights into team performance and workflow health.

## 2. Goals
- Implement "Stale Ticket" detection (no comments within a configurable window).
- Add "Workload Balancer" visualization (Member capacity).
- Add "Bottleneck Analysis" (Average time spent in each status).
- Enhance "System Velocity" (Created vs. Closed trends) across Global and Sector views.
- Ensure all widgets respect existing RBAC and visibility rules.

## 3. Architecture & Data Flow

### 3.1 Backend: Service Layer (`monitor_service.py`)
- **`monitor_stale_tickets(db, principal, hours)`**: 
  - Filter `Ticket` where `status` is in `ACTIVE_STATUSES`.
  - Subquery `TicketComment` to find tickets where `max(created_at) < (now - hours)`.
  - Respect `_visible_stmt(principal)`.
- **`monitor_bottlenecks(db, principal, sector_id, mode, window_days)`**:
  - Aggregate durations from `TicketStatusHistory`.
  - Mode `Live`: Sum time-in-status for open tickets.
  - Mode `Historical`: Avg time-in-status for tickets closed within `window_days`.
- **`monitor_timeseries` (Enhanced)**:
  - Allow `sector_id` filtering to support sector-specific velocity charts in the Monitor page.

### 3.2 Frontend: Widget Components (`DashboardPage.tsx`)
- **`StaleTicketsWidget`**: List view showing ticket code, title, and "Hours since last activity".
- **`WorkloadBalancerWidget`**: ECharts horizontal bar chart showing `Active` vs `Done` tickets per user.
- **`BottleneckWidget`**: ECharts Bar or Pie chart showing duration distribution across statuses.
- **`SystemVelocityWidget`**: Line chart showing daily trends.

### 3.3 Frontend: Monitor Enhancements (`MonitorPage.tsx`)
- **Global Tab**: Move System Velocity to the top level.
- **Sector Tab**: Replace/Augment the Workload table with the new Workload Balancer chart. Add Bottleneck Analysis chart.

## 4. Design & UI
- **ECharts Integration**: Use consistent color palettes (Blue for Active/Created, Green for Done/Closed, Orange for High Priority).
- **Responsive Layout**: Widgets will support the 12-column grid-layout, defaulting to `4x6` or `6x6` sizes.
- **Filtered Config**: Configuration dropdowns for Sectors and Users will only show items the current `Principal` is authorized to see.

## 5. Security & RBAC
- **Principal Visibility**: All queries will use the internal `_visible_stmt` which filters by sector membership and beneficiary relationship.
- **Sensitive Data**: Private comments will be counted for "Stale" detection even if the user can't see the comment body, maintaining accuracy without leaking content.

## 6. Implementation Plan (Next Steps)
1. Update `monitor_service.py` with new aggregate functions.
2. Update `DashboardPage.tsx` with new `WIDGET_TYPES` and Renderers.
3. Update `MonitorPage.tsx` to include the new charts in tabs.
4. Verify data accuracy against existing seeds.
