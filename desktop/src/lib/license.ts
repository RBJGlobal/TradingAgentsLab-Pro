/**
 * License-gate SEAM for Trading Agents Lab Pro.
 *
 * This wires the trial window + the gate call-sites so the founder can drop in
 * Keygen + Ed25519 offline validation later (via the RBJ Global Licensing
 * Integration Playbook) WITHOUT touching any call-site. The key validation
 * itself is a STUB (see `validateLicenseKey`): until the playbook lands, no key
 * validates, so the app runs on the 3-day trial only. This is deliberately not
 * a shipping paywall yet.
 *
 * Design intent (so the later wiring is a drop-in):
 * - `getLicenseStatus()` is the single source of truth every gate reads.
 * - `validateLicenseKey(key)` is the ONE function to replace with real Ed25519
 *   verification; its signature `(key: string) => boolean` stays fixed.
 * - Trial state is local (localStorage). Tamper-resistance (move to a signed
 *   file in userData / OS keychain) is part of the founder's hardening pass,
 *   not this seam.
 */

export const TRIAL_DAYS = 3;
const DAY_MS = 24 * 60 * 60 * 1000;
const TRIAL_START_KEY = 'tal:license:trial-start';
const LICENSE_KEY_KEY = 'tal:license:key';

export type LicenseState = 'trial' | 'licensed' | 'expired';

export interface LicenseStatus {
  state: LicenseState;
  /** Whole days left in the trial (0 when expired); omitted when licensed. */
  trialDaysLeft?: number;
  /** Epoch ms of first launch; omitted when licensed. */
  trialStart?: number;
}

export function getLicenseKey(): string | null {
  try {
    const k = localStorage.getItem(LICENSE_KEY_KEY);
    return k && k.trim() ? k.trim() : null;
  } catch {
    return null;
  }
}

export function saveLicenseKey(key: string): void {
  try {
    localStorage.setItem(LICENSE_KEY_KEY, key.trim());
  } catch {
    /* storage unavailable — non-fatal */
  }
}

export function clearLicenseKey(): void {
  try {
    localStorage.removeItem(LICENSE_KEY_KEY);
  } catch {
    /* non-fatal */
  }
}

/**
 * STUB. Offline license-key validation lives here: Keygen key format + Ed25519
 * signature verification against the RBJ public key. Until wired, it returns
 * false for every key, so the app never claims a "licensed" state it cannot
 * actually verify (fail-closed on licensing, so we don't accidentally give the
 * product away, while the trial still fails-open so a storage hiccup never
 * locks a legitimate user out mid-trial).
 *
 * TODO(license-playbook): replace the body with Ed25519 verify of a
 * Keygen-issued signed key. Keep the `(key: string) => boolean` signature.
 */
export function validateLicenseKey(_key: string): boolean {
  return false;
}

/** Read, lazily initializing on first launch, the trial-start timestamp. */
function trialStart(now: number): number {
  try {
    const raw = localStorage.getItem(TRIAL_START_KEY);
    if (raw) {
      const ts = Number(raw);
      if (Number.isFinite(ts) && ts > 0) return ts;
    }
    localStorage.setItem(TRIAL_START_KEY, String(now));
  } catch {
    /* storage unavailable — fail open to a trial starting now */
  }
  return now;
}

/**
 * Single source of truth for gate decisions. `now` is injectable for tests.
 * A valid stored license => 'licensed'; otherwise the 3-day trial from first
 * launch, and 'expired' past it.
 */
export function getLicenseStatus(now: number = Date.now()): LicenseStatus {
  const key = getLicenseKey();
  if (key && validateLicenseKey(key)) {
    return { state: 'licensed' };
  }
  const start = trialStart(now);
  const elapsedDays = (now - start) / DAY_MS;
  if (elapsedDays >= TRIAL_DAYS) {
    return { state: 'expired', trialDaysLeft: 0, trialStart: start };
  }
  return {
    state: 'trial',
    trialDaysLeft: Math.max(0, Math.ceil(TRIAL_DAYS - elapsedDays)),
    trialStart: start,
  };
}

/** May the user start a run? False only when the trial has expired and no
 * valid license is present. */
export function isRunAllowed(now: number = Date.now()): boolean {
  return getLicenseStatus(now).state !== 'expired';
}
