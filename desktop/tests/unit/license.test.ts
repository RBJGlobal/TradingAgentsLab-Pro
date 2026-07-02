// @vitest-environment happy-dom
//
// Unit tests for the license-gate seam's trial logic. The key validation is a
// stub (fail-closed) until the Keygen/Ed25519 playbook is wired, so these lock
// the trial window countdown + expiry (the part that actually gates runs today)
// and that a stored key never fakes a "licensed" state.
import { afterEach, describe, expect, it } from 'vitest';
import {
  TRIAL_DAYS,
  clearLicenseKey,
  getLicenseStatus,
  isRunAllowed,
  saveLicenseKey,
  validateLicenseKey,
} from '../../src/lib/license';

const DAY = 24 * 60 * 60 * 1000;
const START = 1_000_000_000_000;

afterEach(() => localStorage.clear());

describe('license trial gate', () => {
  it('starts a fresh install in trial with the full window and runs allowed', () => {
    const s = getLicenseStatus(START);
    expect(s.state).toBe('trial');
    expect(s.trialDaysLeft).toBe(TRIAL_DAYS);
    expect(isRunAllowed(START)).toBe(true);
  });

  it('counts down and expires at the window edge', () => {
    getLicenseStatus(START); // initialize first-launch timestamp
    expect(getLicenseStatus(START + 1 * DAY)).toMatchObject({ state: 'trial', trialDaysLeft: 2 });
    // exactly TRIAL_DAYS elapsed -> expired, runs blocked
    expect(getLicenseStatus(START + TRIAL_DAYS * DAY).state).toBe('expired');
    expect(isRunAllowed(START + TRIAL_DAYS * DAY)).toBe(false);
    expect(getLicenseStatus(START + 30 * DAY).state).toBe('expired');
  });

  it('stub validation is fail-closed: no key grants "licensed"', () => {
    expect(validateLicenseKey('KEYGEN-STYLE-KEY')).toBe(false);
    getLicenseStatus(START); // start trial
    saveLicenseKey('KEYGEN-STYLE-KEY');
    // Even with a stored key, once the trial is over the stub cannot validate,
    // so we correctly stay expired rather than granting unverified access.
    expect(getLicenseStatus(START + 30 * DAY).state).toBe('expired');
  });

  it('clearing a key never throws and status stays computable', () => {
    saveLicenseKey('k');
    clearLicenseKey();
    expect(['trial', 'expired', 'licensed']).toContain(getLicenseStatus(START).state);
  });
});
