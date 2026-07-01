/**
 * First smoke: app launches, engine handshake succeeds, status strip
 * reflects the running engine within the retry budget.
 *
 * This single test exercises:
 * - Electron spawn against the built bundle
 * - main.ts → engine-runner.ts spawning the Python sidecar
 * - Renderer → main IPC handshake bridge
 * - StatusStrip polling /health and flipping Engine pill to ok
 * - StatusStrip polling /cost-guard/state and flipping Spend pill to ok
 *
 * If this passes, the harness is correct and the rest of the suite is
 * mostly variations on selector + assertion.
 */
import { test, expect } from './fixtures';

test('app launches and engine handshake reaches ok state', async ({ window }) => {
  // The window's hash defaults to #analyze. Confirm the shell rendered.
  await expect(window.locator('[data-testid="nav-analyze"]')).toBeVisible();

  // Engine pill — starts 'pending', flips to 'ok' once /health succeeds.
  // The retry-with-grace logic in StatusStrip means we may briefly see
  // 'pending' then 'ok'. Waiting for ok with the 20s expect timeout is
  // the right shape.
  const enginePill = window.locator('[data-testid="status-pill-engine"]');
  await expect(enginePill).toBeVisible();
  await expect(enginePill).toHaveAttribute('data-state', 'ok');

  // Spend pill — populated from /cost-guard/state. Starts 'pending'
  // and flips to 'ok' once the engine responds. cap=0 by default so
  // colour is neutral 'ok', not amber/red.
  const spendPill = window.locator('[data-testid="status-pill-spend"]');
  await expect(spendPill).toBeVisible();
  await expect(spendPill).toHaveAttribute('data-state', 'ok');

  // LLM pill — no secrets in the sandbox userDataDir, so it should be
  // 'off' (unconfigured).
  const llmPill = window.locator('[data-testid="status-pill-llm"]');
  await expect(llmPill).toHaveAttribute('data-state', 'off');
});
