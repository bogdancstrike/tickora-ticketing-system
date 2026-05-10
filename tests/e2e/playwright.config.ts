import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for Tickora E2E.
 *
 * The default `BASE_URL` points at the Vite dev server (5173). For staging
 * runs, set `BASE_URL=https://tickora.staging.example` before invoking the
 * test command. `STORAGE_STATE` opts into a pre-authenticated session
 * dumped via `auth.setup.ts`.
 */
export default defineConfig({
  testDir: './specs',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:5173',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'auth',
      testMatch: 'auth.setup.ts',
    },
    {
      name: 'chromium',
      dependencies: ['auth'],
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'tests/e2e/.auth/state.json',
      },
    },
  ],
});
