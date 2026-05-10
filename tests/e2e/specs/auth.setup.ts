/**
 * One-shot login that runs before the test suite and dumps a storage state
 * to disk so subsequent specs can reuse the session without driving the
 * Keycloak login form on every run.
 *
 * Credentials come from env vars so we never hard-code passwords:
 *   TICKORA_USERNAME (default: bogdan)
 *   TICKORA_PASSWORD (default: Tickora123!)
 *
 * The seeded `bogdan` user is the super-admin (full /tickora group).
 */
import { test as setup, expect } from '@playwright/test';

const STATE_PATH = 'tests/e2e/.auth/state.json';

setup('authenticate as bogdan (full platform access)', async ({ page }) => {
  const username = process.env.TICKORA_USERNAME ?? 'bogdan';
  const password = process.env.TICKORA_PASSWORD ?? 'Tickora123!';

  await page.goto('/');

  // Keycloak login form — selectors are the standard ones the realm ships
  // with. If you customise the theme, update these.
  await page.getByLabel(/username|email/i).fill(username);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /sign in|log in/i }).click();

  // Land on the SPA shell.
  await expect(page).toHaveURL(/\/(tickets|monitor|admin|profile)/, { timeout: 15_000 });

  await page.context().storageState({ path: STATE_PATH });
});
