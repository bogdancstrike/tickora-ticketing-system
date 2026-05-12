# Tickora — Security & Performance Review

_Last refreshed: 2026-05-12. Live snapshot of the current branch._

This document is a working snapshot of how Tickora handles security and
performance. It is the place to look for "is X actually defended?" rather
than the design document. Findings are split into:

- **A — RBAC correctness:** can the wrong user do something they shouldn't?
- **B — Defence in depth:** what happens when controllers slip up?
- **C — Performance hotspots:** where the system will fall over first.
- **D — Dashboards & widgets RBAC:** authorization on personal dashboards
  and widget configuration.
- **E — Notifications, SSE, audio alerts:** the real-time surface.
- **F — Attack surface inventory:** what's exposed and how it's gated.
- **G — Hardening backlog:** known gaps with concrete next steps.

---

## A · RBAC correctness

### Strengths (verified 2026-05-12)

| Area | Evidence | Verdict |
|---|---|---|
| Single source of truth for permissions | `src/iam/rbac.py` — 29 pure predicates, no DB calls inside. | ✅ Strong |
| Visibility encoded in SQL, not post-filtered | `ticket_service._visibility_filter` builds an `OR(...)` clause baked into the `SELECT`. A buggy controller can't leak unrelated tickets via list endpoints. | ✅ Strong |
| Permission-aware serializers | `ticketing/serializers.serialize_ticket` strips internal fields (sectors, request IP, source channel, internal user IDs) when `can_see_internal` is false. | ✅ Strong |
| Atomic workflow transitions | Every transition is `UPDATE … WHERE … RETURNING`. Race-free under load; concurrent attempts collapse to one winner + `ConcurrencyConflictError`. | ✅ Strong |
| Audit in the caller's transaction | `audit_service.record(db, …)` shares the caller's session, so audit and state commit or roll back together. Access-denied attempts emit `ACCESS_DENIED` with the failing rule name. | ✅ Strong |
| Self-assignment gate for comments + status | `can_post_public_comment`, `can_post_private_comment`, `can_mark_done`, `can_drive_status` require **active assignment** (or admin / triage role / beneficiary side). Bystander members and chiefs cannot comment or push status without `assign_to_me` first. | ✅ Hardened (2026-05-09) |
| Sector chief admin scope | `admin_service.list_users` now restricts chiefs to users in their managed sectors; password resets and updates use `require_admin_or_chief`. | ✅ Tightened (2026-05-10) |
| Widget catalogue role gating | `dashboard_service.list_widget_definitions(db, p)` filters by `required_roles`; `upsert_widget` re-checks at write time; `auto_configure_dashboard` skips widgets the principal can't use. A beneficiary's picker now contains only the universally-available subset. | ✅ Hardened (2026-05-12) |
| Backend 403 vs frontend gating | Audited the full endpoint matrix (87 endpoints, 19 handler files) against `src/iam/decorators.py`, `rbac.py`, and the service layer. Every restricted operation is enforced server-side; the frontend is purely cosmetic. | ✅ Verified |

### Findings worth attention

- **Email-based external requester identity.** `can_close` / `can_reopen`
  match by email when `beneficiary_type == 'external'`. A reused email could
  authorise close on a long-dormant ticket. Consider pinning
  `beneficiary_user_id` on first contact rather than re-validating email.
- **`is_super_admin`** is sourced from `Config.SUPER_ADMIN_SUBJECTS`
  (env-driven, comma-separated Keycloak subject UUIDs). Hard delete is the
  only operation behind this gate today. Default empty in dev; rotate
  during deploy.
- **Distributor sees private comments.** `can_see_private_comments` allows
  distributors to read private notes during triage. If the role expands
  beyond triage, narrow this predicate to chief/sector-member only.
- **Self-assignment policy implications.** A chief who *needs* to push a
  ticket through state must self-assign first. This is intentional — every
  status change is attributable to a real owner — but it changes the
  operational pattern for chiefs who used to act as fast-path approvers.
  The frontend surfaces the "Assign to me" button prominently when a chief
  hits a blocked transition.

---

## B · Defence in depth

### Reads

1. **SQL filter** — `_visibility_filter` baked into the `SELECT`.
2. **Service predicate** — `can_view_*` re-checked after the row is loaded.
3. **Permission-aware serializer** — strips internal fields per `Principal`.

A controller that forgets a check still cannot leak: any one of the three
catches it.

### Writes

1. **`@require_authenticated`** — extracts bearer JWT or short-lived SSE
   ticket from Redis (`sse_ticket:<uuid>`, TTL 30 s), verifies via JWKS,
   hydrates the `Principal`.
2. **Service predicate** — action-specific check + state-machine transition.
3. **Atomic UPDATE** — encodes the precondition in the `WHERE` clause.
   Returns `ConcurrencyConflictError` (409) when the precondition no longer
   holds.
4. **Audit row** in the same transaction.

### Observability of failures

- `ACCESS_DENIED` audit rows include the failing rule name (e.g.
  `rule: can_post_private_comment`) so forensics can answer "who tried what
  and why was it denied?" without log archeology.
- `audit_service.record` captures `request_ip` and `user_agent` via
  `request_metadata.client_ip()` — trusted-proxy aware (uses
  `TRUSTED_PROXIES` env var; falls back to `remote_addr`).
- Comment edit window (`COMMENT_EDIT_WINDOW = 15 min`) enforced server-side,
  not in the UI.
- **CSRF / origin:** Flask-RESTX is the API surface. Tokens are bearer JWTs
  with PKCE on the SPA, so traditional CSRF is moot. CORS
  (`ALLOWED_ORIGINS`) must be locked down in production.
- **Active session presence.** `src/common/session_tracker` writes per-user
  TTL keys to Redis on every authenticated request. The admin overview
  reads `SCAN tickora:session:active:*`. Presence-only (no PII), 5-minute
  TTL, **never** used as an authZ signal — a Redis blackout returns 0
  instead of denying access.

### Potential improvements

- **Rate limiting** is configured for comments, attachments, and ticket
  review (`RATE_LIMIT_*_PER_MIN`) but not yet applied to `POST /api/tickets`.
  Add a Redis-backed bucket.
- **Soft-delete path** flags `is_deleted = true`. The list query filters by
  `is_deleted = false`, but the audit tab still pulls events regardless of
  soft-delete state. Consider hiding deleted tickets' audit rows from
  non-super-admins.
- **Hard delete** is gated on `is_super_admin` ✓. Add a soft-warning audit
  event each time a super-admin *views* (not just deletes) sensitive data.

---

## C · Performance hotspots

### Recently addressed

- **`/api/tickets` count on 1M+ rows.** Admins/auditors with no narrowing
  filter use `pg_class.reltuples` (kept fresh by autovacuum/ANALYZE) instead
  of a full `COUNT(*)`. Inaccuracy is tiny and bounded; latency cap is hard.
- **`/api/monitor/overview` (8s on 1M+).** Wrapped in a 60-second Redis
  memoisation keyed by visibility class (admin/auditor share one key; sector
  users keyed by sorted sectors; others keyed by user_id). Cache miss falls
  back to a live computation; Redis blackout falls back to live computation.
- **Phase-9 perf indexes** (`migrations/9a1f3e0c2d10_phase9_perf_indexes`):
  - `idx_tickets_active_created_at` partial(`is_deleted = false`)
  - `idx_tickets_active_status_created`, `idx_tickets_active_priority_created`
  - `idx_tickets_active_creator_created`, `idx_tickets_active_sector_created`
  - `idx_ticket_sectors_sector_ticket`, `idx_ticket_assignees_user_ticket`
  - `idx_audit_events_actor_recent`, `idx_ticket_comments_author_recent`
- **Materialized views dropped.** `mv_dashboard_*` were retired in
  `c4d8a72e1f5b_drop_orphan_tables`. Monitor service now uses Redis-cached
  live aggregates exclusively. Worker no longer publishes the
  `refresh_dashboard_mvs` task.
- **SLA subsystem removed** (commit `8e06b9d` / `29a1a0d`). Drops a
  cron job, a column family, and a chart per the BRD scope cut. The hourly
  `sla-checker` deployment can be deleted.

### Likely to hurt next

1. **`reference_service.assignable_users`** — issues a `User × SectorMembership × Sector`
   join with no LIMIT. Cardinality scales with users × memberships. Cap at
   500 rows once the user base passes a few thousand.
2. **`ticket_service._list`** does an extra round trip per page to hydrate
   `current_sector_code` and `beneficiary_user_id`. Maps are bounded by
   `limit`, so impact is sub-millisecond; a join in the main query would
   shave a roundtrip if needed.
3. **Comment listing** hydrates author display names via a single `IN (…)`
   query — fast, but for very long threads consider eager-loading via SQL
   join into a single statement.
4. **Audit explorer global query** has no cursor; `limit` is capped at 200.
   Add a cursor when the table approaches 1M rows. The new
   `idx_audit_events_actor_recent` and entity-type filter help.
5. **`_visibility_filter` for distributors** adds an unconstrained
   `Ticket.status IN ('pending','assigned_to_sector')` clause OR'd into the
   query. The partial `idx_tickets_active_status_created` covers this under
   the `is_deleted = false` partial — verify with `EXPLAIN ANALYZE` on a
   representative dataset.

### Wins worth doing

- Add an index on `audit_events(actor_username)` if username filters become
  common — currently only `actor_user_id` and `(action, created_at)` are
  indexed. The new audit explorer supports username search.
- The SSE producer (`notifications._publish_to_sse_raw`) publishes via
  `enqueue_after_commit`, so the Redis publish only fires after the
  notification row is committed. Eliminates the race where the frontend
  receives an SSE event but a follow-up REST fetch returns stale data.

---

## D · Dashboards & widgets RBAC

### What exists (as of 2026-05-12)

- **`custom_dashboards`** — owned by a single user. The `is_public` column
  was **dropped** in `d5e9b1207f08_drop_is_public_dashboards.py`. Sharing is
  not implemented.
- **`dashboard_widgets`** — child rows. Each widget has a `type` (looked up
  against `widget_definitions`) and a free-form `config` JSONB
  (`{sectorCode, scope, ticketId, limit, hours, …}`).
- **`widget_definitions`** — admin-managed catalogue with `type`,
  `display_name`, `description`, `icon`, `is_active`, `required_roles`.
- **`user_dashboard_settings`** — per-user `is_favorite` / `is_default`
  flag, scoped to dashboards the user owns.
- **`dashboard_shares` removed** in `c4d8a72e1f5b_drop_orphan_tables`.

### Findings

| Concern | Status | Detail |
|---|---|---|
| Owner-only dashboard access | ✅ | `get_dashboard`, `update_dashboard`, `delete_dashboard`, `upsert_widget`, `delete_widget`, `auto_configure_dashboard` all enforce `d.owner_user_id != p.user_id → NotFoundError`. The 404 (vs 403) prevents existence enumeration. |
| Widget `config` write-time validation | ✅ | `dashboard_service._validate_widget_config` runs inside `upsert_widget`. Rejects unknown `scope`, rejects `sector_code` outside `p.all_sectors` (admins/auditors wildcard), routes `ticketId` through `ticket_service.get` so the canonical visibility predicate is the gate. 11 unit tests. |
| Widget data fetches re-check RBAC | ✅ | All widget data endpoints (`monitor_sector`, `monitor_personal`, `list_tickets`, etc.) re-run the same RBAC predicates as direct API calls. Defence in depth even when write-time validation is satisfied. |
| Widget catalogue role gating | ✅ Hardened 2026-05-12 | `GET /api/admin/widget-definitions` filters by the caller's `required_roles` match. `upsert_widget` re-checks via `_check_widget_required_roles`. `auto_configure_dashboard` pre-loads the catalogue and skips any widget the principal cannot use, so a beneficiary's auto-configured dashboard cannot silently include admin-only widgets. |
| Auto-configure leaks across roles | ✅ | `_pick_recipe` branches on `p.is_admin`, `p.is_auditor`, `p.is_distributor`, `p.chief_sectors`, `p.is_internal`. The chief recipe was retitled — `audit_stream` (admin/auditor/distributor-only) replaced with `my_assigned` so chiefs don't get widgets they can't use. |
| `recent_tickets` watcher widgets | ✅ | The watcher list filters via `_visible_stmt(p)` (visibility-aware). Tickets a user can't see don't get widgets. Hard cap of 50 (`_AUTO_CONFIGURE_WATCHER_HARD_CAP`) regardless of `autopilot_max_ticket_watchers` system setting. |

### Beneficiary catalogue (post-2026-05-12)

A beneficiary's widget picker contains only the universally-available
subset: `ticket_list`, `profile_card`, `recent_comments`, `shortcuts`,
`clock`, `welcome_banner`, `notification_feed`, `my_watchlist`,
`my_mentions`, `my_requests`, `requester_status`. Operational widgets
(`monitor_kpi`, `linked_tickets`, `bottleneck_analysis`, `priority_mix`,
`sector_stats`, `stale_tickets`, `throughput_trend`, `user_workload`,
`workload_balancer`) require at least `tickora_internal_user` and are
hidden from beneficiary accounts.

### Recommendations

1. ~~**Validate `widget.config` at write time.**~~ ✅ Implemented 2026-05-10.
2. ~~**Decide on `dashboard_shares`.**~~ ✅ Dropped 2026-05-10.
3. ~~**Decide on `is_public`.**~~ ✅ Column dropped 2026-05-11
   (`d5e9b1207f08_drop_is_public_dashboards.py`).
4. ~~**Cap auto-configure inputs.**~~ ✅ Hard-capped at 50 watchers.
5. ~~**Gate `WidgetDefinition.required_roles`.**~~ ✅ Enforced 2026-05-12 in
   `list_widget_definitions`, `_check_widget_required_roles`, and
   `auto_configure_dashboard`.

---

## E · Notifications, SSE, audio alerts

### Delivery model

1. A worker task (`notify_distributors`, `notify_sector`, `notify_assignee`,
   `notify_ticket_event`, `notify_comment`, `notify_mentions`,
   `notify_unassigned`, `notify_beneficiary`) writes one row per recipient
   in `notifications` (table: `notifications`).
2. After the task's transaction commits, `_publish_to_sse_raw` publishes
   the notification payload to `notifications:{user_id}` on Redis.
3. The browser maintains an SSE connection at `/api/notifications/stream`
   authenticated via a 30-second one-time ticket exchanged at
   `POST /api/notifications/stream-ticket`. Each subscriber receives only
   their channel's events.
4. Distributors and admins receive an audible alert (`/alert.mp3`) on
   `ticket_created` events when the per-user sound toggle in the sidebar
   is enabled (`useSoundStore`, persisted to `localStorage` under
   `tickora-sound`). Other roles never hear the alert.

### Auth on the SSE surface

- `EventSource` cannot send custom headers, so the SPA exchanges its JWT
  for a one-time ticket via POST. The ticket lives in Redis with a 30-second
  TTL and is deleted on first use (`SSE_TICKET_TTL`).
- The bearer extractor in `iam.decorators._extract_bearer` accepts an
  `sse_ticket` query parameter as a fallback, but redeems it once.
- Per-user channel isolation: the worker publishes to `notifications:{user_id}`,
  the subscriber subscribes to its own channel only — no fan-out filter
  needed in the browser.

### Audit

`/api/notifications/stream` doesn't write audit rows (high-frequency
heartbeat surface). The underlying notification rows record every dispatch.
The Profile page shows the user their own notifications; admins use
`/api/audit?action=*` to inspect cross-user activity.

---

## F · Attack surface inventory

| Surface | Exposure | Notes |
|---|---|---|
| `/api/*` | All authenticated calls | 84 authenticated endpoints. Every endpoint goes through `@require_authenticated`; restricted ones add a service-layer gate. |
| `/health`, `/liveness`, `/readiness` | Public | k8s probes. No PII; safe to expose at the LB. |
| `/api/notifications/stream` | Authenticated (via SSE ticket) | Long-lived gevent connection. Heartbeat every 30 s. |
| Attachments | Bytes never via API | Upload via pre-signed `PUT` (5-min TTL) to MinIO. Download via 302 to pre-signed `GET` (60-s TTL). |
| Keycloak admin | Service account only | `tickora-api` confidential client. Realm-management roles minimised to `query-users`, `query-groups`, `view-users`, `view-realm`, `manage-users`. |
| Redis | Internal only | No public exposure. SSE tickets, monitor cache, session tracker, rate-limit buckets, JWKS cache. |
| Kafka | Internal only | Task envelopes. `INLINE_TASKS_IN_DEV=true` runs tasks in-process for dev so Kafka isn't a hard dependency. |
| MinIO | Direct from browser | Pre-signed URLs are credential-scoped. SSE bucket policy + server-side encryption recommended for prod. |
| Postgres | Internal only | PgBouncer in front. Connection pool size capped per replica. |
| `/api/tasks` | Admin only | Returns `tasks` lifecycle rows: payload, attempts, last error. |

---

## G · Hardening backlog

- [ ] Apply rate limiting to `POST /api/tickets`. `POST /api/tickets/<id>/review`
      already has a per-user bucket via `rate_limiter.check(bucket="ticket_review")`.
- [ ] Move `SUPER_ADMIN_SUBJECTS` to a Keycloak group and resolve the list
      from the IAM service rather than env.
- [ ] Trust `X-Forwarded-For` only behind known proxies (configured via
      `TRUSTED_PROXIES`). Currently we still accept the header when the
      env var is empty — should fail closed in prod.
- [ ] Add `pip-audit` and `npm audit` to CI.
- [ ] Plan a dedicated "deleted-ticket" audit policy: who can read history
      after soft-delete?
- [ ] Lock down CORS for prod (default `Config.ALLOWED_ORIGINS` is
      `http://localhost:5173`).
- [ ] Add a regression test that simulates each role attempting every other
      role's endpoints, asserting `403` (or `404` by design).
- [ ] Pin external requester identity to `beneficiary_user_id` on first
      contact rather than re-validating email indefinitely.
- [x] Validate widget `config` at write time. _Done 2026-05-10._
- [x] Decide on `DashboardShare` model — dropped 2026-05-10.
- [x] Drop unused materialized views (`mv_dashboard_*`) — dropped
      2026-05-10. Worker no longer publishes `refresh_dashboard_mvs`.
- [x] Drop the `is_public` column on `custom_dashboards` — dropped
      2026-05-11.
- [x] Gate `WidgetDefinition.required_roles` end-to-end (catalogue list,
      widget upsert, auto-configure). _Done 2026-05-12._
- [x] Sector chief admin scope tightened to managed sectors. _Done 2026-05-10._
- [x] Add `manage-users` to the `tickora-api` service account roles so
      admin password resets stop silently 403'ing on Keycloak. _Done
      2026-05-12._
- [x] Switch SSE publish to `enqueue_after_commit` so the frontend never
      receives a notification for an uncommitted row. _Done 2026-05-12._

---

## Quick test ideas

```python
# tests/integration/test_rbac_matrix.py — TODO
@pytest.mark.parametrize("actor_role,target_action,expected", RBAC_MATRIX)
def test_rbac_matrix(client, actor_role, target_action, expected):
    """Every role × action combination either succeeds (200/201/204) or
    fails with a known refusal code (401/403/404). The matrix is the
    contract — regressions show up here before they reach production."""
    ...
```

```python
# tests/unit/test_widget_role_gating.py — TODO
def test_beneficiary_picker_has_no_operational_widgets(...):
    """A beneficiary calling list_widget_definitions sees only widgets
    where required_roles is empty."""
    ...

def test_chief_auto_configure_skips_audit_stream(...):
    """auto_configure_dashboard filters widgets by required_roles even when
    the recipe lists them."""
    ...
```

A table-driven matrix catches most regressions without touching service
internals — and reads as the design contract when an engineer is wondering
"who's allowed to do X?".
