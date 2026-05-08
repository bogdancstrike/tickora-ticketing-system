# Tickora — Security & Performance Review

_Last refreshed: 2026-05-08. Live audit by Claude on the current branch._

This document is a working snapshot. Findings are split into:

- **A — RBAC correctness:** can the wrong user do something they shouldn't?
- **B — Defence in depth:** what happens when controllers slip up?
- **C — Performance hotspots:** where the system will fall over first.
- **D — Hardening backlog:** known gaps with concrete next steps.

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
| Reviewer restriction (recent) | `review_service` now refuses `assignee_user_id` from a distributor unless they are also admin or the chief of the target sector. | ✅ Fixed in this branch |

### Findings worth attention

- **`is_super_admin` was hardcoded to one subject.** Now sourced from
  `Config.SUPER_ADMIN_SUBJECTS` (env-driven, comma-separated). Rotate the
  default during deployment. Hard delete (`can_delete_ticket`) goes through
  this gate.
- **`assignable_users` over-shared user data.** The endpoint used to allow
  any chief or distributor to enumerate the full user/sector graph. It now
  refuses non-admins without an explicit `sector_code` and rejects requests
  for sectors the caller doesn't belong to (distributors retain cross-sector
  read because they triage everything).
- **`can_close` / `can_reopen` accept email match for external users.** This
  is correct per spec, but it does mean a stale email rebound to another
  external user could authorise a close. Consider hashing or pinning the
  `beneficiary_user_id` on first contact rather than email-based identity for
  long-lived tickets.
- **`can_see_private_comments`** intentionally allows distributors to read
  private notes. If the role expands beyond triage, narrow this to
  `is_chief_of` or sector membership.

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

### Potential improvements

- **Rate limiting** is configured for comments and attachments
  (`RATE_LIMIT_*_PER_MIN`) but not yet applied to ticket creation, which is
  the most abusable endpoint for external beneficiaries. Add a Redis-backed
  bucket on `POST /api/tickets`.
- **Soft-delete path** allows admins to flag `is_deleted = true`. The list
  query filters by `is_deleted = false`, but `_visibility_filter` does not
  re-check, so deletion is complete from a tenant view. **Confirm** the
  audit explorer (`get_for_ticket`) also respects this — currently it
  pulls all events regardless. Consider hiding deleted tickets' audit
  rows from non-super-admins.
- **Hard delete** is gated on `is_super_admin` ✓. Add a soft-warning audit
  event each time a super-admin views (not just deletes) sensitive data —
  helps detect insider misuse.

---

## C · Performance hotspots

### Likely first to hurt

1. **`reference_service.assignable_users`** — issues a `User x SectorMembership x Sector`
   join with no LIMIT. Cardinality scales with users × memberships. Acceptable
   today; cap at 500 rows once the user base passes a few thousand.
2. **`ticket_service._list`** — does an extra round trip per page to hydrate
   `current_sector_code` and `beneficiary_user_id`. The maps are bounded by
   `limit`, so impact is sub-millisecond, but a join in the main query
   (LEFT JOIN sectors / beneficiaries) would shave a roundtrip if needed.
3. **Comment listing** now hydrates author display names via a single
   `IN (...)` query — fast, but for very long threads consider eager-loading
   via SQL join into a single statement.
4. **Audit explorer global query** has no cursor; `limit` is capped at 200,
   sort + filters use indexed columns (`created_at`, `action`, `entity_id`,
   `correlation_id`). Add a cursor when the table approaches 1M rows.
5. **Materialized views** (`mv_dashboard_*`) refresh in the background
   worker. The dashboard endpoints read directly. Verify the refresh cadence
   (`worker.py`) is appropriate for the data freshness SLA — every minute is
   normal, every 5 minutes is fine for a 100-user team.
6. **`_visibility_filter` for distributors** adds an unconstrained
   `Ticket.status IN ('pending','assigned_to_sector')` clause OR'd into the
   query. There's a partial index (`active_by_sector`) but the OR may prevent
   its use. Run `EXPLAIN ANALYZE` against a representative dataset before
   investing in additional indexes.

### Wins worth doing

- Add an index on `audit_events(actor_username)` if username filters become
  common — currently only `actor_user_id` and `(action, created_at)` are
  indexed.
- The notification SSE stream broadcasts to all subscribers; ensure the
  per-user filtering happens server-side (not client-side) for principal
  isolation.

---

## D · Hardening backlog

- [ ] Move `SUPER_ADMIN_SUBJECTS` to a Keycloak group and resolve the list
      from the IAM service rather than env (already configurable, but env is
      not as tamper-proof as a managed group).
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

---

## Quick test ideas

```python
# tests/integration/test_rbac_matrix.py — TODO
@pytest.mark.parametrize("actor_role,target_action,expected", RBAC_MATRIX)
def test_rbac_matrix(client, actor_role, target_action, expected):
    ...
```

A table-driven matrix here would catch most regressions without touching
service internals.
