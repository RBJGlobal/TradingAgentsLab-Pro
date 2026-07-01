/**
 * Sidebar navigation + hash routing.
 *
 * Verifies all four routes mount their root component when clicked,
 * the URL hash updates, and the active nav item carries `data-active`.
 * If any route's root component changes name, only the leaf assertion
 * for that route needs to update.
 */
import { test, expect } from './fixtures';

test('sidebar navigates between all four routes', async ({ window }) => {
  // Wait for shell ready.
  await expect(
    window.locator('[data-testid="status-pill-engine"]'),
  ).toHaveAttribute('data-state', 'ok');

  const routes: Array<{
    nav: string;
    hash: string;
    /** Marker we expect on the route's page once it mounts. */
    marker: string;
  }> = [
    { nav: 'nav-analyze', hash: '#analyze', marker: '[data-testid="analyze-button"]' },
    { nav: 'nav-watchlist', hash: '#watchlist', marker: '[data-testid="watchlist-add-button"]' },
    // History + Settings have no required input fields, just heading text.
    { nav: 'nav-history', hash: '#history', marker: 'h1:has-text("History")' },
    { nav: 'nav-settings', hash: '#settings', marker: 'h1:has-text("Settings")' },
  ];

  for (const r of routes) {
    await window.locator(`[data-testid="${r.nav}"]`).click();
    await expect(window).toHaveURL(new RegExp(`${r.hash}$`));
    await expect(window.locator(`[data-testid="${r.nav}"]`)).toHaveAttribute(
      'data-active',
      'true',
    );
    await expect(window.locator(r.marker).first()).toBeVisible();
  }
});
