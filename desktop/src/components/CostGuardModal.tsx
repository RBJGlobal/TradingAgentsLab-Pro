/**
 * Override modal for CostGuard.
 *
 * Shown when a debate would exceed a configured cap and the user can opt
 * to override for this single session. Anti-tamper: the Override button
 * is disabled for 3 seconds after the modal opens (countdown visible),
 * preventing rage-click bypass. No "remember this for the day" option —
 * each over-cap session needs a fresh click.
 *
 * Cancel is always enabled. Pressing Escape cancels.
 */

import { useEffect, useState } from 'react';

import type { CostGuardConfig, SpendState } from '../lib/cost-guard';
import styles from './CostGuardModal.module.css';

const COUNTDOWN_SECONDS = 3;

export type OverDimension = 'daily' | 'weekly' | 'monthly' | 'rate';

export interface CostGuardModalProps {
  /** Which cap fired. */
  overDimension: OverDimension;
  /** Current spend state at the time the cap was hit. */
  spend: SpendState;
  /** Active config — used to format cap labels. */
  config: CostGuardConfig;
  /** Worst-case estimated cost of the requested session. */
  estCostUsd: number;
  /** Called when the user clicks "Override and continue" (after countdown). */
  onConfirm: () => void;
  /** Called when the user clicks "Cancel" or presses Escape. */
  onCancel: () => void;
}

export function CostGuardModal({
  overDimension,
  spend,
  config,
  estCostUsd,
  onConfirm,
  onCancel,
}: CostGuardModalProps): JSX.Element {
  const [secondsLeft, setSecondsLeft] = useState(COUNTDOWN_SECONDS);

  useEffect(() => {
    if (secondsLeft <= 0) return;
    const t = setTimeout(() => setSecondsLeft((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [secondsLeft]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  const overrideReady = secondsLeft <= 0;

  return (
    <div className={styles.scrim} role="dialog" aria-modal="true" aria-labelledby="cg-modal-title">
      <div className={styles.modal}>
        <h2 id="cg-modal-title" className={styles.title}>
          {overDimension === 'rate' ? 'Session rate cap reached' : 'Budget cap reached'}
        </h2>

        <p className={styles.body}>{describePrimary(overDimension, spend, config, estCostUsd)}</p>

        <div className={styles.capList}>
          <CapRow
            label="Daily"
            current={spend.daily_usd}
            cap={config.cap_daily_usd}
            highlight={overDimension === 'daily'}
          />
          <CapRow
            label="Weekly"
            current={spend.weekly_usd}
            cap={config.cap_weekly_usd}
            highlight={overDimension === 'weekly'}
          />
          <CapRow
            label="Monthly"
            current={spend.monthly_usd}
            cap={config.cap_monthly_usd}
            highlight={overDimension === 'monthly'}
          />
          {config.cap_sessions_per_day > 0 && (
            <SessionCapRow
              count={spend.sessions_today}
              cap={config.cap_sessions_per_day}
              highlight={overDimension === 'rate'}
            />
          )}
        </div>

        <div className={styles.buttons}>
          <button
            type="button"
            className={styles.cancel}
            onClick={onCancel}
            autoFocus
          >
            Cancel
          </button>
          <button
            type="button"
            className={styles.override}
            onClick={onConfirm}
            disabled={!overrideReady}
            aria-disabled={!overrideReady}
          >
            {overrideReady ? 'Override and continue' : `Override (${secondsLeft})`}
          </button>
        </div>

        <p className={styles.hint}>
          Override applies to this session only. Adjust caps in{' '}
          <strong>Settings &rarr; Cost Guard</strong> for permanent changes.
        </p>
      </div>
    </div>
  );
}

// ---- Helpers ----------------------------------------------------------------

function describePrimary(
  dim: OverDimension,
  spend: SpendState,
  config: CostGuardConfig,
  est: number,
): string {
  if (dim === 'rate') {
    return `You've used ${spend.sessions_today} of your ${config.cap_sessions_per_day} sessions today. This session would push you over the limit.`;
  }
  const current =
    dim === 'daily' ? spend.daily_usd : dim === 'weekly' ? spend.weekly_usd : spend.monthly_usd;
  const cap =
    dim === 'daily'
      ? config.cap_daily_usd
      : dim === 'weekly'
        ? config.cap_weekly_usd
        : config.cap_monthly_usd;
  return `You've spent ${formatUsd(current)} of your ${formatUsd(cap)} ${dim} cap. This session may cost up to ${formatUsd(est)} and will exceed the limit.`;
}

function CapRow({
  label,
  current,
  cap,
  highlight,
}: {
  label: string;
  current: number;
  cap: number;
  highlight: boolean;
}): JSX.Element {
  if (cap <= 0) return <></>; // disabled cap — don't show
  const pct = Math.min(100, (current / cap) * 100);
  const overPct = pct >= 100;
  return (
    <div className={`${styles.capRow} ${highlight ? styles.capRowHighlight : ''}`}>
      <span className={styles.capLabel}>{label}</span>
      <div className={styles.capProgress}>
        <div
          className={`${styles.capBar} ${overPct ? styles.capBarOver : pct >= 80 ? styles.capBarWarn : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={styles.capValue}>
        {formatUsd(current)} / {formatUsd(cap)}
      </span>
    </div>
  );
}

function SessionCapRow({
  count,
  cap,
  highlight,
}: {
  count: number;
  cap: number;
  highlight: boolean;
}): JSX.Element {
  const pct = Math.min(100, (count / cap) * 100);
  const overPct = pct >= 100;
  return (
    <div className={`${styles.capRow} ${highlight ? styles.capRowHighlight : ''}`}>
      <span className={styles.capLabel}>Sessions</span>
      <div className={styles.capProgress}>
        <div
          className={`${styles.capBar} ${overPct ? styles.capBarOver : pct >= 80 ? styles.capBarWarn : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={styles.capValue}>
        {count} / {cap}
      </span>
    </div>
  );
}

function formatUsd(value: number): string {
  if (value >= 100) return `$${value.toFixed(0)}`;
  if (value >= 10) return `$${value.toFixed(2)}`;
  if (value >= 1) return `$${value.toFixed(2)}`;
  if (value >= 0.01) return `$${value.toFixed(3)}`;
  return `$${value.toFixed(4)}`;
}
