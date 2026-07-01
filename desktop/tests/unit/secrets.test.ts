/**
 * Unit tests for the secrets module's corruption-recovery path (Tier 2,
 * 2026-05-24).
 *
 * The previous behavior: a corrupt secrets.json threw on every Settings read,
 * blanking the page indefinitely. New behavior: detect, back up the unreadable
 * original to `secrets.json.corrupt-<iso>.bak`, return an empty store, and
 * surface a banner via the `secrets:recovered` IPC so the user knows to
 * re-enter their keys (their previous entries are intact in the backup).
 *
 * `electron` and `node:fs` are mocked so no real disk touched.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Hoisted shared state the vi.mock factories below close over. Each test
// reassigns _files / _safe / _kept so tests are independent.
const h = vi.hoisted(() => {
  return {
    _files: new Map<string, string>(),
    _renames: [] as Array<{ from: string; to: string }>,
    _unlinks: [] as string[],
    _writes: [] as Array<{ path: string; data: string }>,
    _safeAvailable: true,
  };
});

vi.mock('electron', () => ({
  app: {
    getPath: () => '/tmp/tal-userdata',
  },
  safeStorage: {
    isEncryptionAvailable: () => h._safeAvailable,
    encryptString: (s: string) => Buffer.from(`enc:${s}`),
    decryptString: (b: Buffer) => b.toString('utf8').replace(/^enc:/, ''),
  },
}));

vi.mock('node:fs', () => {
  // secrets.ts uses `import fs from 'node:fs'` (default import), so every
  // method has to live on the `default` export as well as on named exports
  // for any other call style.
  const fsImpl = {
    existsSync: (p: string) => h._files.has(p),
    readFileSync: (p: string) => {
      const v = h._files.get(p);
      if (v === undefined) throw new Error(`ENOENT: ${p}`);
      return v;
    },
    writeFileSync: (p: string, data: string) => {
      h._writes.push({ path: p, data });
      h._files.set(p, data);
    },
    renameSync: (from: string, to: string) => {
      h._renames.push({ from, to });
      const v = h._files.get(from);
      if (v !== undefined) {
        h._files.set(to, v);
        h._files.delete(from);
      }
    },
    copyFileSync: (from: string, to: string) => {
      const v = h._files.get(from);
      if (v !== undefined) h._files.set(to, v);
    },
    unlinkSync: (p: string) => {
      h._unlinks.push(p);
      h._files.delete(p);
    },
    mkdirSync: () => {},
  };
  return { default: fsImpl, ...fsImpl };
});

const SECRETS_FILE = '/tmp/tal-userdata/secrets.json';

beforeEach(() => {
  vi.resetModules();
  h._files.clear();
  h._renames.length = 0;
  h._unlinks.length = 0;
  h._writes.length = 0;
  h._safeAvailable = true;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('corrupt secrets recovery', () => {
  it('returns empty listings + records recovery when JSON is malformed', async () => {
    h._files.set(SECRETS_FILE, '{not really json');
    const { listSecrets, getCorruptionRecovery } = await import(
      '../../electron/secrets'
    );

    const rows = listSecrets();
    expect(rows).toEqual([]);

    const info = getCorruptionRecovery();
    expect(info).not.toBeNull();
    expect(info?.backupPath).toMatch(/secrets\.json\.corrupt-.*\.bak$/);
    expect(typeof info?.recoveredAt).toBe('string');
  });

  it('backs up the corrupt file via rename', async () => {
    h._files.set(SECRETS_FILE, '{not really json');
    const { listSecrets } = await import('../../electron/secrets');

    listSecrets();

    expect(h._renames.length).toBeGreaterThanOrEqual(1);
    const rename = h._renames[0];
    expect(rename.from).toBe(SECRETS_FILE);
    expect(rename.to).toMatch(/secrets\.json\.corrupt-.*\.bak$/);
  });

  it('recovers from a file missing the version field', async () => {
    h._files.set(SECRETS_FILE, JSON.stringify({ entries: {} }));
    const { listSecrets, getCorruptionRecovery } = await import(
      '../../electron/secrets'
    );

    expect(listSecrets()).toEqual([]);
    expect(getCorruptionRecovery()).not.toBeNull();
  });

  it('fires the onSecretsRecovered listener exactly once at recovery time', async () => {
    h._files.set(SECRETS_FILE, '{not really json');
    const { listSecrets, onSecretsRecovered } = await import(
      '../../electron/secrets'
    );

    const listener = vi.fn();
    onSecretsRecovered(listener);

    listSecrets();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener.mock.calls[0][0].backupPath).toMatch(/\.bak$/);

    // Calling listSecrets again doesn't fire the listener twice (the file is
    // now valid empty JSON, no further recovery needed).
    listSecrets();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it('leaves valid files untouched and reports no recovery', async () => {
    h._files.set(
      SECRETS_FILE,
      JSON.stringify({
        version: 1,
        entries: {
          'llm:openai': {
            hint: '…abcd',
            updatedAt: '2026-05-20T00:00:00Z',
            cipher: 'ZW5jOnNrLWFiY2RlZmdo',
          },
        },
      }),
    );
    const { listSecrets, getCorruptionRecovery } = await import(
      '../../electron/secrets'
    );

    const rows = listSecrets();
    expect(rows).toEqual([
      { key: 'llm:openai', hint: '…abcd', updatedAt: '2026-05-20T00:00:00Z' },
    ]);
    expect(getCorruptionRecovery()).toBeNull();
    expect(h._renames).toEqual([]);
  });

  it('still throws on forward-incompatible version (no silent downgrade)', async () => {
    // A future app wrote v999. We do NOT recover — silently overwriting would
    // drop fields the newer app added. Loud throw is intentional here.
    h._files.set(
      SECRETS_FILE,
      JSON.stringify({ version: 999, entries: {} }),
    );
    const { listSecrets } = await import('../../electron/secrets');

    expect(() => listSecrets()).toThrow(/newer than/);
  });
});
