# Tickora Security And Performance Review

_Last refreshed: 2026-05-12. Current branch snapshot._

This is a rough security review of the application as it exists now, not a
target architecture. It intentionally calls out places where the current code
does not meet the product story or where security depends on operational
discipline outside the repository.

## Executive Summary

Tickora has a solid start: Keycloak JWT validation, server-side RBAC predicates,
SQL visibility filters for ticket lists, audit rows for many write paths,
owner-scoped dashboards, MinIO signed URLs, correlation IDs, and a real service
layer rather than business logic in controllers.

It is not ready to be treated as a hardened production security boundary. The
highest-risk issues are authorization bugs in admin user management and audit
history, weak workflow invariants, attachment validation that trusts client
metadata, and async task behavior that can publish work before the caller's
transaction commits when Kafka mode is used.

## Highest Priority Findings

| Severity | Area | Finding | Impact | Fix direction |
|---|---|---|---|---|
| Critical | Admin/RBAC | Sector chiefs can reach `admin_service.update_user()`, and the payload path can assign realm roles including `tickora_admin`. | A sector chief may be able to grant platform admin privileges to a managed user. | Split user profile edits from role management. Make realm-role changes root-admin only, and deny adding/removing privileged roles outside `/tickora`. |
| Critical | Audit/RBAC | `GET /api/tickets/<id>/audit` authorizes ordinary ticket viewers through `ticket_service.get()` and then returns audit rows. It does not enforce `can_view_audit_tab()`. | Beneficiaries/requesters can potentially read old/new values, metadata, IP addresses, user agents, actor details, and internal workflow history. | Gate ticket audit with `rbac.can_view_audit_tab()` or a stricter predicate. Add regression tests for requester, external requester, watcher, member, chief, distributor, auditor. |
| High | IAM | Local `users.is_active = false` is not enforced during `principal_from_claims()`. Keycloak disable failures are swallowed in some admin update paths. | A locally deactivated user can continue authenticating if Keycloak still issues tokens. | Fail closed on inactive local users or make Keycloak the sole status source. Do not swallow Keycloak disable/enable errors. |
| High | Workflow | The state machine allows transitions from every status to every status, and `assign_to_me` currently accepts all statuses. | A sector user who can view an unassigned `done` or `cancelled` ticket can self-assign it and move it to `in_progress`, bypassing reopen/cancel rules. | Restrict `assign_to_me` to `pending` and `assigned_to_sector`, and make `change_status` enforce a real transition table. |
| High | Workflow | Any active assignee can use the generic status change path to set any status, including `pending`, `assigned_to_sector`, `done`, or `cancelled`. | Assignees can bypass reason requirements and workflow-specific validation except where the service adds one-off checks. | Replace all-status transitions with explicit allowed edges and per-target validators. |
| High | Attachments | Upload size, content type, checksum, and AV status are metadata-level checks. MinIO does not enforce the claimed size limit, and registration does not verify actual object size/checksum/content. | A user can upload oversized or malicious content and register benign metadata. | Verify object stat at registration, store checksum, enforce allowed MIME/magic bytes, and run a real scan before downloadable status. |
| High | Attachments | Registering an attachment only checks that a referenced comment belongs to the ticket. It does not verify the comment is visible to the caller, not deleted, or authored by the caller. | A ticket viewer who learns a comment id can attach files to another user's private or deleted comment. | Require comment visibility plus edit/post authority for the target comment. Reject deleted comments. |
| High | Dashboards | `dashboard_service.delete_widget()` checks `w.dashboard_id == dashboard_id` but does not verify the parent dashboard owner. | A user who knows another user's dashboard id and widget id pair can delete that widget. | Load the dashboard by owner first, then delete only child widgets under that owned dashboard. |
| High | Tasking | In Kafka mode, `tasking.publish()` writes/sends outside the caller's transaction and can send before the caller commits. | Notifications/tasks can observe missing rows, run after a rollback, or produce user-visible messages for changes that never committed. | Make `publish()` transaction-aware by default. Create task rows in the caller session and send after commit, or use an outbox. |
| Medium | Notifications | Private comment notifications exclude the requester side but still include watchers. | A watcher who should not see private comments may learn that a private internal comment happened. | Filter private comment notification recipients through `can_see_private_comments()`. |
| Medium | SSE auth | The bearer extractor accepts `sse_ticket` query parameters on all authenticated endpoints, not only the notification stream endpoint. | A stolen one-time SSE ticket can authenticate one arbitrary API request within 30 seconds. | Redeem SSE tickets only in the stream endpoint or bind the ticket to path/method. |
| Medium | Rate limiting | Config has comment and attachment rate-limit variables, but only ticket create and review use the limiter. The limiter fails open on Redis outage. | Write spam and upload-url abuse are easier than the config suggests. | Apply limiters to comments, attachment URL/register, metadata writes, password reset, and review. Decide fail-open vs fail-closed per endpoint. |
| Medium | Review flow | The review endpoint is admin/distributor-gated at the top, but private comment and cancel branches call services that require active assignee. | Documented triage operations can fail at runtime or behave inconsistently by role. | Either update predicates for review-specific behavior or remove unsupported review payload options. |
| Medium | Endorsements | Direct endorsement requests only check target user existence/activity, not that the target has `tickora_avizator`. `claim()` is not an atomic conditional update. | Requests can be assigned to users who cannot decide them; concurrent claims can race. | Validate target role and implement claim as `UPDATE ... WHERE assigned_to_user_id IS NULL RETURNING`. |
| Medium | Frontend/API | `deleteTicketMetadata` calls `DELETE /api/tickets/<id>/metadata/<key>`, while the backend endpoint is `DELETE /api/tickets/<id>/metadata?key=...`. | Metadata deletion from the UI can be broken even when backend authorization is correct. | Align the frontend client with `src/api/metadata.py`. |
| Medium | Packaging | Pydantic `EmailStr` requires `email-validator`, but `requirements.txt` does not list it explicitly. | Clean installs can fail depending on transitive dependency state. | Add `email-validator` to backend requirements. |
| Low | Audit quality | Priority-change audit records can log the new priority as both old and new after reload. | Forensics lose the previous priority. | Capture old value before update/reload. |
| Low | Makefile/docs | `make sla-checker` points at removed `sla_checker.py`. | Developer confusion and failed local commands. | Remove the target or make it print that SLA is removed. |

## Verified Strengths

| Area | Current behavior |
|---|---|
| Authentication | All `/api/*` handlers import and use `@require_authenticated`. Public endpoints are limited to `/health`, `/liveness`, and `/readiness`. |
| Token verification | JWTs are verified against Keycloak JWKS with issuer/audience/expiry checks. Principal hydration maps realm roles and Keycloak groups into a local `Principal`. |
| Ticket list visibility | `ticket_service._visibility_filter()` encodes visibility into SQL for list queries. It avoids "load too much then filter in Python" for the primary ticket list surface. |
| Server-side authorization | RBAC predicates live in `src/iam/rbac.py`, and service methods call predicates before mutations. Frontend route guards are not the security boundary. |
| Correlation and request metadata | Correlation ID middleware is present. `request_metadata.client_ip()` is trusted-proxy-aware and fails closed to `remote_addr` when `TRUSTED_PROXIES` is empty. |
| Signed attachment URLs | The API authorizes before issuing presigned PUT/GET URLs. Downloads return short-lived signed redirects instead of proxying bytes through Flask. |
| Owner dashboards | Dashboard list/get/update/delete/upsert paths generally enforce `owner_user_id == principal.user_id` and use `404` for non-owners. The widget delete bug above is the exception. |
| Widget catalog | `WidgetDefinition.required_roles` is filtered at list time and checked at widget upsert/auto-configure time. |
| Global audit | `/api/audit` and `/api/users/<id>/audit` require admin/auditor. The per-ticket audit endpoint is the current weak point. |
| Notifications | Notification rows are per-recipient and list/mark-read endpoints are scoped to `principal.user_id`. |

## Attack Surface Inventory

| Surface | Exposure | Notes |
|---|---|---|
| `/health`, `/liveness`, `/readiness` | Public | No authentication. Should not include secrets or dependency credentials. |
| `/api/*` | Authenticated | 108 authenticated API method registrations in `maps/endpoint.json`. Service-layer gates vary by domain. |
| `/api/notifications/stream-ticket` | Authenticated | Stores the raw bearer JWT in Redis under a one-time 30-second ticket. |
| `/api/notifications/stream` | Authenticated by SSE ticket | Long-lived gevent/EventSource connection. Redis outage can break stream setup. |
| Attachments | Browser to MinIO using signed URLs | API never sees bytes. This is good for scale but makes registration-time object verification mandatory. |
| Keycloak Admin REST | Backend service account | Used for user/group/role management and password reset. Errors must not be swallowed on security-sensitive changes. |
| Redis | Internal | JWT/principal cache, monitor cache, presence, rate limits, SSE tickets, pub/sub. Most callers fail open. |
| Kafka | Internal | Task envelopes. In non-inline mode, publish timing is not currently transaction-safe. |
| MinIO/S3 | Direct signed URL access | Bucket CORS uses `ALLOWED_ORIGINS` or `*` if config is empty. Lock this down in production. |
| Postgres | Internal | Canonical data store and audit/task lifecycle tables. |
| `/api/tasks` | Admin only | Exposes task payloads and last errors; keep admin-only and avoid secrets in payloads. |

## RBAC Review

### Identity And Principal Construction

- Realm roles come from `realm_access.roles`.
- `/tickora` root group implies admin-like behavior and `has_root_group`.
- User type is role-based: `tickora_external_user` means external; otherwise
  users are treated as internal for many checks.
- Group parsing accepts `/tickora/sectors/<code>`,
  `/tickora/sectors/<code>/member(s)`, and `/tickora/sectors/<code>/chief(s)`.
- Current code treats the bare sector group `/tickora/sectors/<code>` as chief
  access, not as both member and chief. This is a documentation/expectation
  trap because some older text described it as effective chief+member.
- If token groups do not include the root tree, IAM may fetch Keycloak groups.
  If the token already carries `/tickora`, it does not fetch extra groups for
  the `Principal`; `/api/me` performs a separate expansion for display.

### Ticket Visibility

`can_view_ticket()` currently grants visibility to:

- admin or auditor;
- external requester by email match;
- creator;
- beneficiary user;
- sector intersection;
- distributor for `pending` or `assigned_to_sector`.

Assignment alone is not a visibility grant. That matters: if a user is assigned
outside their sector membership, they can be the assignee but fail to view the
ticket through `can_view_ticket()`. Assignment logic should ensure target users
can actually see the target ticket.

### Mutation And Workflow

The code deliberately makes most operator writes assignee-owned:

- public comments: active assignee, creator, beneficiary, or external requester;
- private comments: active assignee only;
- mark done, close, cancel, reopen, generic status drive: active assignee only;
- priority change: admin, distributor, or chief of current sector;
- sector assignment: admin, distributor, or chief of current sector;
- user assignment/reassignment: admin, distributor, or chief of current sector.

This design makes actions attributable, but it creates two practical issues:

- admins/chiefs/distributors often must self-assign before doing operator-side
  work;
- the generic all-status transition path undercuts the intended workflow
  discipline.

### Admin Surface

Admin APIs are inconsistent by design and by accident:

- Some endpoints require `/tickora` root group through `require_admin()`.
- Some endpoints only check `principal.is_admin`.
- User list/get/update/reset-password allow sector chiefs for managed users.
- Role mutation is not safely separated from profile mutation. This is the
  critical escalation risk.

Fix the role-management split before adding more admin UI features.

## Attachment Review

Current safe parts:

- Upload URL generation requires ticket visibility.
- Filenames are normalized/sanitized.
- Requested size is checked before issuing a URL.
- Registration checks that the object exists.
- Download authorizes through ticket/comment visibility before returning a
  signed GET redirect.
- Attachment visibility derives from the parent comment visibility.

Current unsafe parts:

- A signed PUT does not enforce actual object size in the application.
- Registration does not compare object size with declared `size_bytes`.
- There is no checksum verification.
- MIME/content-type is trusted too much.
- AV scan is a stub and sets `is_scanned=True`, `scan_result="clean"`.
- Comment attachment registration does not verify comment author/edit rights.
- Private/deleted comment attachment abuse is possible if a comment id leaks.

Minimum production bar:

- issue presigned uploads with constrained headers;
- stat the object at registration;
- calculate or require checksum;
- enforce allowed MIME and magic bytes;
- keep unscanned attachments non-downloadable;
- scan asynchronously with a real scanner;
- delete orphan objects that never register.

## Audit Review

The audit model is useful, but current access control is too broad for ticket
audit. Audit rows can include:

- actor user id and username;
- entity ids and ticket ids;
- old and new value snapshots;
- metadata payloads;
- request IP;
- user agent;
- correlation id.

That data is often more sensitive than the ticket's public fields. The global
audit explorer is correctly admin/auditor only. The per-ticket audit endpoint
must not be available to every ticket viewer.

The table is a normal SQLAlchemy table with indexes. It is not currently a
monthly partitioned audit ledger despite older architecture text claiming that.
Plan partitioning/retention before high-volume deployment.

## Notifications And SSE Review

Current model:

1. Service methods publish task names such as `notify_distributors`,
   `notify_sector`, `notify_assignee`, `notify_comment`, and
   `notify_beneficiary`.
2. Task handlers write `notifications` rows.
3. After the task transaction commits, notification handlers publish Redis SSE
   events to `notifications:{user_id}`.
4. The SPA opens an EventSource using a short-lived Redis ticket because
   EventSource cannot send authorization headers.

Problems:

- In Kafka mode, task publication can happen before the caller's transaction
  commits. That is the bigger issue than SSE publication inside the task.
- Notification rows do not have a uniqueness/idempotency constraint.
- Private comment notification recipient selection can leak private activity to
  watchers who cannot read the private comment.
- The one-time SSE ticket is accepted by the generic bearer extractor, not only
  by the stream route.
- The stream generator assumes Redis is available; Redis outages can break the
  stream path rather than gracefully falling back.
- Stream connections do not write audit rows. That is reasonable for heartbeats,
  but ticket issuance should be observable.

## Performance Review

Known good choices:

- Ticket list visibility is pushed into SQL.
- Page sizes are bounded.
- Monitor overview uses short Redis caching with role-aware keys.
- Recent Phase 9 indexes cover common active-ticket list filters and audit
  recency patterns.
- Redis cache paths are treated as optional for availability.

Likely hotspots:

- `reference_service.assignable_users` can return broad user/sector joins
  without a hard result cap.
- Global audit explorer is limit-capped but not cursor-paginated for very large
  tables.
- Distributor visibility includes a broad status clause over all pending and
  sector-assigned tickets; verify plans on representative data.
- Comment threads can grow without pagination pressure if long operational
  threads become common.
- SSE connections are long-lived gevent work. Capacity test with real proxies
  before depending on it for many users.
- Kafka-mode task races can cause retries/failures that look like performance
  issues but are really consistency bugs.

Claims that should not be made yet:

- Do not claim `/metrics` is exposed. `prometheus-client` is installed, but a
  route/instrumentation surface was not found.
- Do not claim audit monthly partitioning. The model is a regular table.
- Do not claim attachment MIME/magic/AV enforcement. It is not there yet.
- Do not claim notification idempotency without a database constraint.
- Do not claim all write endpoints are rate-limited. They are not.

## Configuration Review

| Setting | Current behavior | Security note |
|---|---|---|
| `ALLOWED_ORIGINS` | Defaults to `http://localhost:5173`. If `*` is configured, CORS reflects origins with credentials. | Never use wildcard credentials in production. |
| `TRUSTED_PROXIES` | Empty by default; X-Forwarded-For is ignored unless the peer is trusted. | This is correct fail-closed behavior. Populate it behind ingress. |
| `SUPER_ADMIN_SUBJECTS` | Defaults to a hard-coded seed subject UUID. | Move to a Keycloak group or deployment secret; remove hard-coded production subjects. |
| `ATTACHMENT_PRESIGNED_TTL` | Defaults to 60 seconds for upload and download. | Keep short; constrain uploads more tightly. |
| `INLINE_TASKS_IN_DEV` | Defaults to dev mode. Inline tasks run after commit. | Kafka mode needs outbox semantics. |
| `RATE_LIMIT_*` | Ticket create and review use limiter. Comment/attachment vars exist but are not wired. | Wire all high-risk writes. |

## Hardening Backlog

1. Block sector-chief role escalation through `update_user()`.
2. Gate ticket audit with `can_view_audit_tab()` or stricter.
3. Enforce local disabled users or make Keycloak status authoritative and fail
   closed on Keycloak update errors.
4. Fix workflow transitions: no all-status graph, no assigning closed/cancelled
   tickets without an explicit reopen path.
5. Fix generic status change so it cannot bypass reason/endorsement checks.
6. Implement attachment object stat, checksum, MIME/magic, and real AV scan.
7. Fix attachment-to-comment authorization.
8. Fix dashboard widget deletion owner check.
9. Replace Kafka-mode immediate publish with transaction-safe outbox or
   after-commit task creation/send.
10. Restrict SSE tickets to the stream route and bind ticket to path/method.
11. Apply rate limiting to comments, attachments, metadata writes, password
   reset, and notification ticket issuance.
12. Add idempotency constraints for notification fanout.
13. Validate endorsement targets have `tickora_avizator` and make claim atomic.
14. Align frontend metadata delete URL with backend.
15. Add `email-validator` to backend dependencies.
16. Remove or neutralize stale `make sla-checker`.
17. Add audit retention and partitioning strategy.
18. Add dependency scanning (`pip-audit`, `npm audit`) to CI.
19. Add role-by-endpoint regression tests for every meaningful persona.
20. Add browser/build checks for routes hidden by `RequireRole` to ensure UI
    drift does not hide backend bugs.

## Test Plan Gaps

Minimum tests to add next:

- `test_chief_cannot_grant_tickora_admin`.
- `test_inactive_local_user_cannot_authenticate` or an explicit test proving
  Keycloak is the sole active-state source.
- `test_beneficiary_cannot_read_ticket_audit`.
- `test_external_requester_cannot_read_ticket_audit`.
- `test_assign_to_me_rejects_done_and_cancelled`.
- `test_change_status_rejects_invalid_edges`.
- `test_private_comment_notification_does_not_reach_unprivileged_watcher`.
- `test_attachment_register_rejects_private_comment_without_private_access`.
- `test_attachment_register_rejects_deleted_comment`.
- `test_dashboard_delete_widget_requires_owner`.
- `test_kafka_publish_does_not_send_before_commit` or an outbox unit test.
- `test_endorsement_direct_target_must_be_avizator`.
- `test_endorsement_claim_concurrency`.
- `test_metadata_delete_frontend_path_matches_backend_contract`.

## Production Readiness Verdict

Do not deploy this branch as-is for sensitive data. The application has enough
structure to harden efficiently, but the current authorization and workflow
bugs are material. Fix the critical/high findings first, then use the RBAC
matrix as a regression contract before widening the user population.
