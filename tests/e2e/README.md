# Tickora E2E (Playwright)

End-to-end smoke for the SPA's golden paths. The suite is **smoke** by
design — coarse assertions that catch a broken build or regression in the
biggest user flows. Detailed UI assertions belong in component-level tests.

## First-time setup

```bash
cd tests/e2e
npm install
npx playwright install chromium
```

## Running

The default `BASE_URL` points at the Vite dev server. You need:

* the backend running (`make backend`)
* the frontend dev server running (`cd frontend && npm run dev`)
* the seeded `bogdan` super-admin user available via Keycloak
  (`make keycloak-bootstrap`)

```bash
cd tests/e2e
npm test                      # headless
npm run test:headed           # watch the browser
npm run report                # open the HTML report
BASE_URL=https://staging.example npm test
```

## Auth

`specs/auth.setup.ts` runs once before the suite, drives the Keycloak
login form with the seeded credentials, and saves the storage state to
`.auth/state.json`. Subsequent specs reuse that state so tests run fast.

Override the credentials with env vars if you point at a non-seeded
realm:

```bash
TICKORA_USERNAME=alice TICKORA_PASSWORD=… npm test
```

## What's covered

* Lists tickets at `/tickets` (works on empty seed too).
* Opens a ticket detail when at least one row exists.
* Admin overview renders the `Active sessions` KPI we added in the
  2026-05-09 admin refresh.
* Monitor page does not throw a "Rendered more hooks" error (regression
  guard for the hooks-order bug fixed on 2026-05-09).

## What's not covered yet

* Create-ticket wizard — multi-step UI is a stable target; add when the
  wizard stops changing weekly.
* Comment / attachment upload flows — needs MinIO test bucket.
* Multi-role flows (distributor reviews, chief reassigns) — needs more
  seeded personas. The wire-level role matrix in
  `tests/integration/test_http_role_matrix.py` covers the same shape via
  the API.
