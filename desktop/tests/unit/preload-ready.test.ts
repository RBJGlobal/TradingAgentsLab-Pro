/**
 * Unit tests for waitForPreload (the dev cold-boot preload-race guard).
 *
 * The race itself (vite-plugin-electron spawning Electron before the preload
 * bundle is written) is a process-timing condition that can't be reproduced
 * deterministically in a unit test. What we CAN pin is the helper's contract,
 * which is what main.ts relies on: present-now resolves fast, appears-later
 * resolves when it shows up, never-appears resolves false at the timeout
 * (never hangs).
 */
import { afterEach, describe, expect, it } from 'vitest';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { waitForPreload } from '../../electron/preload-ready';

describe('waitForPreload', () => {
  const dirs: string[] = [];
  function tmp(): string {
    const d = mkdtempSync(path.join(tmpdir(), 'preload-ready-'));
    dirs.push(d);
    return d;
  }
  afterEach(() => {
    for (const d of dirs.splice(0)) {
      try {
        rmSync(d, { recursive: true, force: true });
      } catch {
        // best-effort
      }
    }
  });

  it('resolves true immediately when the preload already exists (warm relaunch)', async () => {
    const p = path.join(tmp(), 'preload.mjs');
    writeFileSync(p, '// preload');
    const start = Date.now();
    await expect(waitForPreload(p, 1000, 10)).resolves.toBe(true);
    // Must not have polled/waited — it was already there.
    expect(Date.now() - start).toBeLessThan(100);
  });

  it('resolves true once the preload appears mid-wait (cold boot)', async () => {
    const p = path.join(tmp(), 'preload.mjs');
    setTimeout(() => writeFileSync(p, '// preload'), 80);
    await expect(waitForPreload(p, 2000, 10)).resolves.toBe(true);
  });

  it('resolves false after the timeout if the preload never appears (build failure)', async () => {
    const p = path.join(tmp(), 'never-written.mjs');
    const start = Date.now();
    await expect(waitForPreload(p, 150, 10)).resolves.toBe(false);
    // Waited roughly the timeout — never hangs, never returns early-true.
    expect(Date.now() - start).toBeGreaterThanOrEqual(140);
  });
});
