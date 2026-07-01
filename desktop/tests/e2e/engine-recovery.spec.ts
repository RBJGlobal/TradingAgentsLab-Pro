/**
 * Tier 1 engine-recovery smoke (2026-05-23).
 *
 * The merge gate for the engine-spawn lifecycle work: prove the app survives a
 * hard engine crash. We launch the app, wait for the Engine pill to reach 'ok',
 * read the engine's pid from the pidfile it now writes, SIGKILL it, and assert:
 *
 *   1. The Engine pill recovers to 'ok' on its own (lazy respawn driven by the
 *      StatusStrip health poll + the engine:exited cache invalidation).
 *   2. The respawned engine is a *new* process (pidfile pid changed), proving
 *      we actually relaunched the sidecar rather than reusing a dead handle.
 *
 * Electron stays up the whole time — no window reload, no app quit.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { test, expect } from './fixtures';

function readEnginePid(userDataDir: string): number | null {
  try {
    const raw = readFileSync(path.join(userDataDir, 'engine.pid'), 'utf-8').trim();
    const pid = Number.parseInt(raw, 10);
    return Number.isInteger(pid) && pid > 0 ? pid : null;
  } catch {
    return null;
  }
}

test('app respawns the engine after a hard crash (kill -9)', async ({
  window,
  sandboxDir,
}) => {
  // Generous budget: baseline + crash + respawn + a slow Electron teardown.
  test.setTimeout(90_000);
  const userDataDir = path.join(sandboxDir, 'userData');
  const enginePill = window.locator('[data-testid="status-pill-engine"]');

  // Healthy baseline.
  await expect(enginePill).toHaveAttribute('data-state', 'ok', { timeout: 20_000 });

  const originalPid = readEnginePid(userDataDir);
  expect(originalPid, 'engine should have written a pidfile by the time it is ok').not.toBeNull();

  // Hard-kill the sidecar out from under the app. SIGKILL can't be caught, so
  // there's no clean shutdown — exactly the crash case Tier 1 must recover from.
  process.kill(originalPid as number, 'SIGKILL');

  // The pill should recover to 'ok' on its own. Recovery is bounded by the
  // StatusStrip slow health poll (10s) + engine cold start (~2-3s); 30s is a
  // comfortable ceiling that still fails loudly if respawn is broken.
  await expect(enginePill).toHaveAttribute('data-state', 'ok', { timeout: 30_000 });

  // And it must be a genuinely new process, not the dead handle.
  await expect
    .poll(() => readEnginePid(userDataDir), { timeout: 10_000 })
    .not.toBe(originalPid);
});
