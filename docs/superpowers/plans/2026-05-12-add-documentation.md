# Add Documentation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the documentation task by adding comprehensive docstrings and JSDoc comments to the specified files in both backend and frontend.

**Architecture:** This is a pure documentation task. No functional changes will be made to the code. Python files will receive triple-quote docstrings, and TypeScript files will receive JSDoc-style comments.

**Tech Stack:** Python (Backend), TypeScript/React (Frontend).

---

### Task 1: Document Backend IAM Service

**Files:**
- Modify: `src/iam/service.py`

- [ ] **Step 1: Enhance `get_or_create_user_from_claims` docstring**

```python
def get_or_create_user_from_claims(claims: dict[str, Any]) -> User:
    \"\"\"
    Upsert a `users` row keyed on `keycloak_subject`.

    This function synchronizes the local database with the Identity Provider (Keycloak).
    It either creates a new user record or updates an existing one with the latest
    claims from the verified token, including username, email, and name fields.

    Args:
        claims: A dictionary containing verified JWT claims. Must contain 'sub'.

    Returns:
        A detached User model instance with the updated data.

    Raises:
        ValueError: If the 'sub' claim is missing.
    \"\"\"
```

- [ ] **Step 2: Enhance `principal_from_claims` docstring**

```python
def principal_from_claims(claims: dict[str, Any]) -> Principal:
    \"\"\"
    Build a Principal from verified token claims, provisioning the user if needed.

    This function is the primary entry point for hydrating a user's security context.
    It performs the following steps:
    1. Attempts to retrieve a cached Principal from Redis using a key derived from the token.
    2. If not cached, it ensures the user exists in the local database.
    3. Resolves the user's effective roles and sector memberships from token claims and Keycloak.
    4. Constructs a new Principal object and caches it in Redis for the duration of the token's validity.

    Args:
        claims: A dictionary containing verified JWT claims.

    Returns:
        A hydrated Principal object representing the authenticated user.
    \"\"\"
```

- [ ] **Step 3: Commit**

```bash
git add src/iam/service.py
git commit -m "docs: enhance docstrings in iam service"
```

---

### Task 2: Document Backend Ticketing Notifications

**Files:**
- Modify: `src/ticketing/notifications.py`

- [ ] **Step 1: Enhance `notify_distributors` docstring**

```python
@register_task("notify_distributors")
def notify_distributors(payload: Dict[str, Any]):
    \"\"\"
    Notify all distributors and admins about a new ticket.

    This task is typically triggered when a new ticket is created. It fetches all
    users with the 'tickora_admin' or 'tickora_distributor' roles from Keycloak,
    maps them to local users, and creates in-app notifications for each.

    Args:
        payload: Dictionary containing 'ticket_id'.
    \"\"\"
```

- [ ] **Step 2: Enhance `_publish_to_sse` docstring**

```python
def _publish_to_sse(user_id: str, notification: Notification):
    \"\"\"
    Publish notification to Redis for SSE delivery.

    Serializes the notification data and publishes it to a Redis channel specific
    to the user (notifications:{user_id}). This enables real-time delivery to
    connected frontend clients via Server-Sent Events.

    Args:
        user_id: The ID of the user to receive the notification.
        notification: The Notification model instance to publish.
    \"\"\"
```

- [ ] **Step 3: Commit**

```bash
git add src/ticketing/notifications.py
git commit -m "docs: enhance docstrings in ticketing notifications"
```

---

### Task 3: Document Frontend Dashboard Page

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Add JSDoc to `WidgetRenderer`**

```typescript
/**
 * A registry component that maps widget types to their respective implementation components.
 * It acts as a dispatcher for rendering different types of widgets based on the provided configuration.
 * 
 * @param {Object} props - The component props.
 * @param {DashboardWidgetDto} props.widget - The widget data and configuration to render.
 */
function WidgetRenderer({ widget }: { widget: DashboardWidgetDto }) {
```

- [ ] **Step 2: Add JSDoc to `autoConfig` mutation in `DashboardDetail`**

```typescript
  /**
   * Mutation to automatically configure the dashboard widgets based on user roles and assignments.
   * Supports 'append' (add recommended widgets) or 'replace' (start from scratch) modes.
   */
  const autoConfig = useMutation({
```

- [ ] **Step 3: Add JSDoc to `DashboardDetail`**

```typescript
/**
 * Component for viewing and editing the details of a specific custom dashboard.
 * Manages the grid layout, widget lifecycle (add, remove, configure), and title editing.
 * Uses react-grid-layout for a responsive and draggable/resizable dashboard experience.
 * 
 * @param {Object} props - The component props.
 * @param {string} props.dashboardId - The unique identifier of the dashboard to display.
 * @param {() => void} props.onBack - Callback function to navigate back to the dashboard list.
 */
function DashboardDetail({ dashboardId, onBack }: { dashboardId: string, onBack: () => void }) {
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx
git commit -m "docs: add JSDoc to DashboardPage components"
```

---

### Task 4: Document Frontend Monitor Page

**Files:**
- Modify: `frontend/src/pages/MonitorPage.tsx`

- [ ] **Step 1: Add JSDoc to `SectorPanel`**

```typescript
/**
 * Displays operational metrics and charts for a specific sector.
 * Includes status and priority breakdowns, oldest tickets list, workload analysis,
 * and bottleneck insights for the selected sector.
 * 
 * @param {Object} props - The component props.
 * @param {MonitorSector} props.sector - The sector monitoring data.
 * @param {React.ReactNode} [props.controls] - Optional UI controls (e.g., sector/user selectors).
 */
function SectorPanel({ sector, controls }: { sector: MonitorSector; controls?: React.ReactNode }) {
```

- [ ] **Step 2: Add JSDoc to `timeseriesOption` useMemo in `MonitorPage`**

```typescript
  /**
   * Generates the ECharts configuration for the historical ticket volume chart.
   * Tracks 'Created' vs 'Closed' tickets over the selected time period.
   * Recalculates whenever the overview data changes.
   */
  const timeseriesOption = useMemo(() => {
```

- [ ] **Step 3: Add JSDoc to `MonitorPage`**

```typescript
/**
 * The primary operational monitoring interface for Tickora.
 * Provides multiple views (Global, Distribution, Sector, User) depending on permissions.
 * Aggregates live metrics, historical trends, and workload distribution to give
 * supervisors and operators a high-level view of system health and performance.
 */
export function MonitorPage() {
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/MonitorPage.tsx
git commit -m "docs: add JSDoc to MonitorPage components"
```

---

### Task 5: Document Frontend Tickets Page

**Files:**
- Modify: `frontend/src/pages/TicketsPage.tsx`

- [ ] **Step 1: Add JSDoc to `TicketsPage`**

```typescript
/**
 * The main ticket listing page featuring a searchable, sortable, and filterable table.
 * Allows users to browse the ticket queue, apply operational filters (status, priority, sector),
 * and navigate to individual ticket details.
 */
export function TicketsPage() {
```

- [ ] **Step 2: Add JSDoc to `TicketDetailPage`**

```typescript
/**
 * Wrapper component for the ticket details view.
 * Extracts the ticket ID from the URL parameters and manages the initial session bootstrap.
 */
export function TicketDetailPage() {
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/TicketsPage.tsx
git commit -m "docs: add JSDoc to TicketsPage components"
```

---

### Task 6: Document Frontend Common Components

**Files:**
- Modify: `frontend/src/components/common/StatusChanger.tsx`
- Modify: `frontend/src/components/common/NotificationDropdown.tsx`

- [ ] **Step 1: Add JSDoc to `StatusChanger`**

```typescript
/**
 * A specialized component for managing ticket status transitions.
 * It enforces the state machine rules defined in the backend, ensuring only
 * valid transitions are available based on the user's role and the ticket's current state.
 * Supports both tag-like dropdowns and button-style interfaces.
 * 
 * @param {Object} props - The component props.
 * @param {TicketDto} props.ticket - The ticket instance whose status is being changed.
 * @param {'small' | 'middle'} [props.size] - The size of the UI element.
 * @param {'tag' | 'button'} [props.mode] - The display mode of the component.
 */
export function StatusChanger({
```

- [ ] **Step 2: Add JSDoc to `NotificationDropdown`**

```typescript
/**
 * A global component for receiving and managing real-time notifications.
 * It maintains a persistent SSE (Server-Sent Events) connection to the backend to
 * receive live updates. It also handles notification persistence, read status tracking,
 * and provides navigation to relevant ticket pages.
 */
export function NotificationDropdown() {
```

- [ ] **Step 3: Add JSDoc to SSE connection logic in `NotificationDropdown`**

```typescript
    /**
     * Establishes and manages the Server-Sent Events (SSE) connection for real-time notifications.
     * Uses a two-step handshake:
     * 1. POST to /stream-ticket to obtain a short-lived SSE token.
     * 2. Initialize EventSource with the obtained token.
     * Handles incoming messages, updates local state, and triggers UI alerts (notifications/sound).
     */
    const connectSSE = async () => {
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/common/StatusChanger.tsx frontend/src/components/common/NotificationDropdown.tsx
git commit -m "docs: add JSDoc to common components"
```
