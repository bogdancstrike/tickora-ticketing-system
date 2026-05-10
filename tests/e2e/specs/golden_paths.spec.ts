/**
 * Golden-path E2E smoke. Each test exercises one user-visible workflow
 * end-to-end. Keep them coarse and resilient — they're tripwires, not
 * full UI specs.
 */
import { test, expect } from '@playwright/test';

test.describe('Golden paths', () => {
  test('lists tickets', async ({ page }) => {
    await page.goto('/tickets');
    // Header is always present once the page renders.
    await expect(page.getByRole('heading', { name: /tickets/i })).toBeVisible();
    // Either a populated table or an empty-state — both are valid landings.
    await expect(
      page.getByText(/no tickets match|total \d+ tickets/i)
    ).toBeVisible({ timeout: 15_000 });
  });

  test('opens a ticket from the list', async ({ page }) => {
    await page.goto('/tickets');
    // Click the first row if present; skip the assertion otherwise so an
    // empty seed doesn't fail the smoke.
    const rows = page.locator('tr.tickora-row-clickable');
    const count = await rows.count();
    test.skip(count === 0, 'No tickets seeded — skipping detail smoke.');
    await rows.first().click();
    await expect(page).toHaveURL(/\/tickets\/[0-9a-f-]{36}/);
  });

  test('admin overview renders the active sessions KPI', async ({ page }) => {
    await page.goto('/admin');
    // KPI strip we added in the 2026-05-09 admin refresh.
    await expect(page.getByText(/active sessions/i)).toBeVisible({ timeout: 15_000 });
  });

  test('monitor page loads without hooks-order errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (err) => errors.push(err.message));
    await page.goto('/monitor');
    await expect(page.getByRole('tab', { name: /global|sector|user/i }).first()).toBeVisible({
      timeout: 20_000,
    });
    expect(errors.filter((e) => /Rendered more hooks/.test(e))).toEqual([]);
  });
});
