/**
 * Playwright config for end-to-end smoke tests against the built Electron app.
 *
 * Why a built bundle and not dev mode:
 * - Production builds load from dist/index.html via file://, with no Vite
 *   dev server, no HMR, no reload-on-source-change. Tests get a stable
 *   target. The tradeoff is you must `npm run build` before testing —
 *   the `test:e2e` script does this for you.
 *
 * Why workers: 1:
 * - Each test launches its own Electron + Python engine sidecar. The
 *   engine binds to a random port chosen by the OS, so two concurrent
 *   Electrons would each spawn their own engine — but secrets storage,
 *   the SQLite DB, and the userData dir would collide across workers
 *   unless we partitioned them deeper. Single-worker is the simple,
 *   correct call. Suite is small (5-8 tests, ~30s total).
 *
 * Why expect timeout 20s:
 * - The engine handshake retry window in renderer + StatusStrip totals
 *   ~11s on cold start. Default 5s flakes on first run.
 */
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/e2e',
  // No parallelism — see header comment.
  workers: 1,
  // Each test runs its own Electron; spread them across files freely.
  fullyParallel: false,
  // Engine startup + first WS frame can take a beat on cold start.
  timeout: 60_000,
  expect: {
    timeout: 20_000,
  },
  // No retry by default. If you see a flake, fix it — don't paper over.
  retries: 0,
  reporter: process.env.CI ? 'github' : 'list',
  use: {
    // Capture trace on failure so post-mortem doesn't require re-running.
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
});
