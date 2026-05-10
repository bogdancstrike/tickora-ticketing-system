# Tickora — Security & Performance Review

_Last refreshed: 2026-05-09. Audit by Claude on the current branch._

This document is a working snapshot. Findings are split into:

- **A — RBAC correctness:** can the wrong user do something they shouldn't?
- **B — Defence in depth:** what happens when controllers slip up?
- **C — Performance hotspots:** where the system will fall over first.
- **D — Dashboards & widgets RBAC:** authorization on personal/shared dashboards and widget configuration.
- **E — Hardening backlog:** known gaps with concrete next steps.

---

## A · RBAC correctness

### Strengths

| Area | Evidence | Verdict |
|---|---|---|
| Single source of truth for permissions | `src/iam/rbac.py` — every check goes through pure predicates. | ✅ Strong |
| Visibility encoded in SQL, not post-filtered | `ticket_service._visibility_filter` builds an `OR(...)` clause baked into the `SELECT`. A buggy controller can't leak unrelated tickets via list endpoints. | ✅ Strong |
| Permission-aware serializers | `ticketing/serializers.serialize_ticket` strips internal fields when `can_see_internal` is false (sectors, IP, source, internal user IDs). | ✅ Strong |
| Atomic transitions | `workflow_service.assign_to_me` and friends use `UPDATE … WHERE status IN (…) RETURNING id` — race-free under load (verified by 50-greenlet integration test). | ✅ Strong |
| Audit always in the same transaction | `audit_service.record(db, …)` shares the caller's session, so audit and state changes commit or roll back together. | ✅ Strong |
| Reviewer restriction | `review_service` refuses `assignee_user_id` from a distributor unless they are also admin or the chief of the target sector. | ✅ |
| **Self-assignment gate for comments + status** | As of 2026-05-09, `can_post_public_comment`, `can_post_private_comment`, `can_mark_done`, and `can_drive_status` require **active assignment** (or admin override / triage role / beneficiary side). Bystander members and chiefs of the sector cannot comment or change status without first pulling the ticket via `assign_to_me`. | ✅ Hardened |

### Findings worth attention

- **Email-based external requester identity.** `can_close` / `can_reopen`
  match by email when `beneficiary_type == 'external'`. A reused email could
  authorise close on a long-dormant ticket. Consider pinning
  `beneficiary_user_id` on first contact rather than re-validating email.
- **`is_super_admin`** is sourced from `Config.SUPER_ADMIN_SUBJECTS`
  (env-driven, comma-separated). Hard delete (`can_delete_ticket`) is the
  only operation behind this gate today. Rotate the default during deploy.
- **Distributor sees private comments.** `can_see_private_comments` allows
  distributors to read private notes for triage. If the role expands beyond
  triage, narrow this predicate to chief/sector-member only.
- **Self-assignment policy implications.** Tightening `can_drive_status` to
  active assignees only means a chief who *needs* to push a ticket through
  state must self-assign first. This is intentional — every status change is
  now attributable to a real owner — but it does change the operational
  pattern for chiefs who used to act as fast-path approvers. The frontend
  needs to surface the "Assign to me" button prominently for chiefs hitting
  blocked status changes.

---

## B · Defence in depth

- All workflow endpoints route through `_check_visible` before the RBAC
  check, so an unauthorised caller cannot distinguish "ticket exists" from
  "ticket exists and is forbidden." Audit `ACCESS_DENIED` events still record
  the attempt — useful for forensics, but be mindful of log volume.
- `audit_service.record` captures `request_ip` and `user_agent` from the live
  Flask request via headers + `remote_addr`. If you put Tickora behind a
  reverse proxy, lock `X-Forwarded-For` parsing to a trusted set of proxies
  (right now we accept whatever the client sends).
- Attachments are uploaded directly to MinIO via presigned URLs and only
  *registered* through the API. We currently store `is_scanned: false` on
  registration; any download endpoint should refuse to redirect when the AV
  pipeline (Phase 8) is wired up and `scan_result != "clean"`.
- Comment edit window (`EDIT_WINDOW = 15 min`) is enforced server-side, not
  in the UI. Good.
- **CSRF / origin:** Flask-RESTX is the API surface. Tokens are bearer JWTs
  with PKCE on the SPA, so traditional CSRF is moot. Verify CORS
  (`ALLOWED_ORIGINS`) is locked down in production.
- **Active session presence.** `src/core/session_tracker` writes per-user
  TTL keys to Redis on every authenticated request. The admin overview
  (`active_sessions` KPI) reads `SCAN tickora:session:active:*`. The data is
  presence-only (no PII), TTL'd at 5 minutes, and never used as an authZ
  signal — a Redis blackout returns 0 instead of denying access.

### Potential improvements

- **Rate limiting** is configured for comments and attachments
  (`RATE_LIMIT_*_PER_MIN`) but not yet applied to ticket creation. Add a
  Redis-backed bucket on `POST /api/tickets`.
- **Soft-delete path** allows admins to flag `is_deleted = true`. The list
  query filters by `is_deleted = false`, but `_visibility_filter` does not
  re-check, so deletion is complete from a tenant view. The audit
  (`get_for_ticket`) currently pulls all events regardless of soft-delete
  state. Consider hiding deleted tickets' audit rows from non-super-admins.
- **Hard delete** is gated on `is_super_admin` ✓. Add a soft-warning audit
  event each time a super-admin *views* (not just deletes) sensitive data.

---

## C · Performance hotspots

### Recently addressed (2026-05-09)

1. **`/api/tickets` count on 1M+ rows.** `ticket_service._list` previously
   tried to count over a visibility-filtered subquery on every page render,
   plus the function was importing `func` indirectly and broke at runtime
   (NameError → frontend showed `0 tickets`). Two changes landed:
   - Added the missing `func` import and the `total_count` return value.
   - For admin/auditor with no narrowing filter we now use
     `pg_class.reltuples` (kept fresh by autovacuum/ANALYZE) instead of a
     full `COUNT(*)`. Inaccuracy is tiny and bounded; latency cap is hard.
2. **`/api/monitor/overview` (8s on 1M+).** Wrapped in a 60-second Redis
   memoisation keyed by visibility class (admin/auditor share, sector users
   keyed by sorted sectors, others keyed by user_id). Cache miss falls back
   to a live computation, Redis blackout falls back to live computation.
3. **Phase-9 perf indexes** (`migrations/9a1f3e0c2d10_phase9_perf_indexes`):
   - `idx_tickets_active_created_at` partial(`is_deleted = false`)
   - `idx_tickets_active_status_created`, `idx_tickets_active_priority_created`
   - `idx_tickets_active_creator_created`, `idx_tickets_active_sector_created`
   - `idx_ticket_sectors_sector_ticket`, `idx_ticket_assignees_user_ticket`
   - `idx_audit_events_actor_recent`, `idx_ticket_comments_author_recent`

### Likely to hurt next

1. **`reference_service.assignable_users`** — issues a `User × SectorMembership × Sector`
   join with no LIMIT. Cardinality scales with users × memberships. Cap at
   500 rows once the user base passes a few thousand.
2. **`ticket_service._list`** does an extra round trip per page to hydrate
   `current_sector_code` and `beneficiary_user_id`. Maps are bounded by
   `limit`, so impact is sub-millisecond; a join in the main query
   would shave a roundtrip if needed.
3. **Comment listing** hydrates author display names via a single `IN (…)`
   query — fast, but for very long threads consider eager-loading via SQL
   join into a single statement.
4. **Audit explorer global query** has no cursor; `limit` is capped at 200.
   Add a cursor when the table approaches 1M rows.
5. **Materialized views** (`mv_dashboard_*`) still exist in migrations but
   are no longer read by runtime monitor code — they only consume disk and
   refresh cycles. **Action:** drop them in a follow-up migration unless a
   future rebuild surfaces a need.
6. **`_visibility_filter` for distributors** adds an unconstrained
   `Ticket.status IN ('pending','assigned_to_sector')` clause OR'd into the
   query. The new partial `idx_tickets_active_status_created` covers this
   under the `is_deleted = false` partial — verify with `EXPLAIN ANALYZE`
   on a representative dataset.

### Wins worth doing

- The notification SSE stream broadcasts to all subscribers; per-user
  filtering must happen server-side (not client-side) for principal
  isolation. Verify the producer in `notifications.py`.
- Add an index on `audit_events(actor_username)` if username filters become
  common — currently only `actor_user_id` and `(action, created_at)` are
  indexed.

---

## D · Dashboards & widgets RBAC

Custom dashboards and widgets are a large new surface area; this section
documents the authorization model as of 2026-05-09.

### What exists

- **`custom_dashboards`** — owned by a single user. Each dashboard has a
  `is_public` flag (currently only used in the serializer, not in any list
  query). Owner is identified by `owner_user_id`.
- **`dashboard_widgets`** — child rows on a dashboard. Each widget has a
  `type` (looked up against the `widget_definitions` catalogue) and a
  free-form `config` JSON dict (e.g. `{"sectorCode": "s10", "scope": "sector"}`).
- **`dashboard_shares`** — model exists with foreign keys to user and
  sector targets, but **no service code uses it** at present. Either wire
  it up or delete the model in cleanup.

### Findings

| Concern | Status | Detail |
|---|---|---|
| Owner-only dashboard access | ✅ | `get_dashboard`, `update_dashboard`, `delete_dashboard`, `upsert_widget`, `delete_widget`, `auto_configure_dashboard` all enforce `d.owner_user_id != p.user_id → NotFoundError`. The 404 (vs 403) prevents existence enumeration. |
| `is_public` flag honored on read | ⚠️ Inert | The flag is settable but `list_dashboards` only returns `owner_user_id == p.user_id`. No public-listing endpoint exists. Either remove the flag or add a `list_public_dashboards` endpoint with explicit RBAC. |
| `dashboard_shares` model orphaned | ⚠️ | The table is migrated but never read or written by service code. Decide: implement sharing UI + service, or drop the table to avoid an attractive nuisance for a future contributor who wires it up incorrectly. |
| **Widget `config` is validated at write time** | ✅ Fixed (2026-05-10) | `dashboard_service._validate_widget_config` runs inside `upsert_widget`. It rejects unknown `scope` values, rejects `sector_code`/`sectorCode` outside the principal's sector set (admin/auditor still wildcard), and routes `ticketId`/`ticket_id` through `ticket_service.get` so the canonical visibility predicate is the gate. Tests in `tests/unit/test_widget_config_validation.py`. |
| Widget data fetches re-check RBAC | ✅ | All widget data endpoints (`monitor_sector`, `monitor_personal`, `list_tickets`) re-run the same RBAC predicates as direct API calls — defence in depth even when the write-time validator is satisfied. |
| Auto-configure leaks across roles | ✅ | `auto_configure_dashboard` branches on `p.is_admin`, `p.chief_sectors`, `p.is_internal`. The widgets it auto-creates only reference sectors the principal already chiefs (`primary_sector or list(p.chief_sectors)[0]`). Internal users get personal-scope widgets only. |
| `recent_tickets` watcher widgets | ✅ | The watcher list filters via `_visible_stmt(p)` (visibility-aware). Tickets a user can't see don't get widgets created. |
| Widget catalogue `required_roles` | ⚠️ | `WidgetDefinition.required_roles` is stored but not currently enforced when adding a widget — any user can add any widget type. The catalogue is mostly UX gating; tighten if roles diverge meaningfully. |
| System settings read via `get_setting` | ⚠️ | `auto_configure_dashboard` reads `autopilot_max_ticket_watchers` from the system settings table. There is no per-user cap, so a malicious script could bump the value to a huge number before triggering auto-configure. Cap server-side (`min(value, 50)`) regardless of the setting. |

### Recommendations

1. ~~**Validate `widget.config` at write time.**~~ ✅ Implemented 2026-05-10
   in `dashboard_service._validate_widget_config`. Rejects unknown `scope`,
   foreign `sector_code`, and invisible `ticketId` (delegates to
   `ticket_service.get`). 11 unit tests.
2. ~~**Decide on `dashboard_shares`.**~~ ✅ Dropped 2026-05-10 (model +
   table) in `c4d8a72e1f5b_drop_orphan_tables`. If sharing is needed in
   the future, design RBAC end-to-end first.
3. **Decide on `is_public`.** Either implement a public listing endpoint
   (with admin gate, since "public" inside a tenanted system needs careful
   thought) or drop the column.
4. **Cap auto-configure inputs.** `auto_configure_dashboard` should hard-
   cap `max_watchers` regardless of the system setting.
5. **Optional: gate `WidgetDefinition.required_roles`.** Reject
   `upsert_widget` when `widget_definition.required_roles` is non-empty and
   the principal lacks the role. This is a UX nicety today (the data still
   won't render) but a cleaner contract long-term.

---

## E · Hardening backlog

- [ ] Move `SUPER_ADMIN_SUBJECTS` to a Keycloak group and resolve the list
      from the IAM service rather than env.
- [ ] Apply rate limiting to `POST /api/tickets` and `POST /api/tickets/<id>/review`.
- [ ] Trust `X-Forwarded-For` only behind known proxies; otherwise fall
      back to `remote_addr`.
- [ ] Add `pip-audit` and `npm audit` to CI (already in TODO Phase 0).
- [ ] Plan a dedicated "deleted-ticket" audit policy: who can read history
      after soft-delete?
- [ ] Lock down CORS for prod (default in `Config.ALLOWED_ORIGINS` is
      `http://localhost:5173`).
- [ ] Add a regression test that simulates each role attempting every other
      role's endpoints, asserting they get 403 (or 404 by design).
- [x] Validate widget `config` at write time (Section D). _Done 2026-05-10._
- [x] Decide on `DashboardShare` model — dropped in
      `c4d8a72e1f5b_drop_orphan_tables`.
- [x] Drop unused materialized views (`mv_dashboard_*`) — dropped in
      `c4d8a72e1f5b_drop_orphan_tables`. Worker no longer publishes the
      `refresh_dashboard_mvs` task.

---

## Quick test ideas

```python
# tests/integration/test_rbac_matrix.py — TODO
@pytest.mark.parametrize("actor_role,target_action,expected", RBAC_MATRIX)
def test_rbac_matrix(client, actor_role, target_action, expected):
    ...
```

```python
# tests/unit/test_dashboard_widget_config.py — TODO
def test_widget_config_rejects_foreign_sector(...):
    """A sector-3 user cannot write a widget config targeting sector 2."""
    ...
```

A table-driven matrix here would catch most regressions without touching
service internals.
