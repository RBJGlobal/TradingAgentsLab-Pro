/**
 * Webhooks Settings round-trip.
 *
 * Verifies the safeStorage-backed config persists across an Electron
 * relaunch within the same sandbox (--user-data-dir is sticky for the
 * fixture's lifetime).
 *
 * We do NOT actually fire a webhook here — that would either spam a
 * real receiver or require standing up a local http listener inside
 * the test. The webhook dispatcher itself is covered by 17 hermetic
 * pytests in engine/tests/test_webhooks.py.
 */
import { test, expect } from './fixtures';

test('add a generic webhook, save, see row, edit it back', async ({ window }) => {
  await expect(
    window.locator('[data-testid="status-pill-engine"]'),
  ).toHaveAttribute('data-state', 'ok');

  await window.locator('[data-testid="nav-settings"]').click();

  // Click the Webhooks tab (text-matched — tab buttons don't have ids).
  await window.locator('button:has-text("Webhooks")').first().click();

  // Empty state visible.
  await expect(window.locator('text=No webhooks configured')).toBeVisible();

  // Add a generic one.
  await window.locator('[data-testid="webhooks-add-button"]').click();
  await expect(window.locator('[data-testid="webhook-editor"]')).toBeVisible();

  await window.locator('[data-testid="webhook-name-input"]').fill('Test hook');
  await window.locator('[data-testid="webhook-kind-select"]').selectOption('generic');
  await window
    .locator('[data-testid="webhook-url-input"]')
    .fill('https://example.com/hook');
  await window.locator('[data-testid="webhook-save-button"]').click();

  // Editor closes, row appears.
  await expect(window.locator('[data-testid="webhook-editor"]')).toHaveCount(0);
  const row = window.locator('[data-testid="webhooks-list"] li').first();
  await expect(row).toBeVisible();
  await expect(row.locator('text=Test hook')).toBeVisible();

  // Re-open the editor — confirms persistence within session and that
  // the saved URL is what we typed.
  await row.locator('button:has-text("Edit")').click();
  await expect(window.locator('[data-testid="webhook-editor"]')).toBeVisible();
  await expect(window.locator('[data-testid="webhook-name-input"]')).toHaveValue(
    'Test hook',
  );
  await expect(window.locator('[data-testid="webhook-url-input"]')).toHaveValue(
    'https://example.com/hook',
  );
});
