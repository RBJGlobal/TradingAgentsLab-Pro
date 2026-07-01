/**
 * Watchlist add → deep-link → analyze handoff.
 *
 * Verifies the watchlist's "Analyze" deep-link plumbs the ticker via
 * sessionStorage into the Analyze page on next render.
 */
import { test, expect } from './fixtures';

test('add ticker to watchlist, deep-link to Analyze, remove it', async ({ window }) => {
  await expect(
    window.locator('[data-testid="status-pill-engine"]'),
  ).toHaveAttribute('data-state', 'ok');

  await window.locator('[data-testid="nav-watchlist"]').click();

  // Add AAPL.
  await window.locator('[data-testid="watchlist-ticker-input"]').fill('AAPL');
  await window.locator('[data-testid="watchlist-add-button"]').click();

  // Row should appear.
  const row = window.locator('[data-testid="watchlist-row-AAPL"]');
  await expect(row).toBeVisible();

  // Deep-link to Analyze. The handoff is via sessionStorage so the
  // ticker should pre-fill on the next mount of Analyze.
  await row.locator('button:has-text("Analyze")').click();
  await expect(window.locator('[data-testid="ticker-input"]')).toHaveValue('AAPL');

  // Back to Watchlist, remove the entry.
  await window.locator('[data-testid="nav-watchlist"]').click();
  window.once('dialog', (d) => d.accept()); // confirm() — preempt by accepting if any
  await window
    .locator('[data-testid="watchlist-row-AAPL"]')
    .locator('button:has-text("Remove")')
    .click();
  await expect(row).toHaveCount(0);
});
