I fixed a substantial first wave of the security gaps, but I’m blocked from finishing the last small edit
  and final verification because the tool runner is now rejecting commands with a usage-limit error until May
  13, 2026 12:47 AM.

  Implemented fixes include:

  - Blocked sector chiefs from mutating realm roles through update_user.
  - Made Keycloak enable/disable and role changes fail closed instead of silently swallowing errors.
  - Enforced inactive local users during principal hydration.
  - Tightened per-ticket audit to require audit-tab visibility, not ordinary ticket visibility.
  - Restricted SSE tickets to the notification stream route.
  - Tightened workflow transitions and blocked self-assigning done/cancelled tickets.
  - Fixed priority-change audit old/new values.
  - Added attachment object size verification and comment-level authorization.
  - Fixed dashboard widget delete owner check.
  - Added attachment/comment rate limits.
  - Fixed direct endorsement target role validation and atomic claim.
  - Fixed frontend ticket metadata delete URL.
  - Added email-validator.
  - Disabled stale make sla-checker.
  - Added regression tests for the above.

  Verified before the tool block:

  - py_compile passed.
  - Full unit suite passed: 283 passed.
  - Targeted integration suite passed: 38 passed, 1 skipped.
  - Frontend build passed.

  Remaining known issue before final clean pass:

  - tests/integration/test_notifications.py was failing because the test patches old _publish_to_sse, while
    the code uses _publish_to_sse_raw. I had the fix ready: add a compatibility wrapper or update the test to
    patch _publish_to_sse_raw. The edit was blocked by the usage-limit rejection.
  - After that, rerun notification tests and a final syntax/unit pass.

  Also note: there are staged deletions I did not create or touch: docs/TODO.md, docs/brd.md, docs/
  implementation_plan.md.

---

sse_ticket in redis holds the jwt (unsecure)