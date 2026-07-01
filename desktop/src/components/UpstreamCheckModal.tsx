/**
 * Upstream check result modal — shown after the user clicks Help → Check
 * for Updates or Settings → About → Check for updates.
 *
 * Three states:
 * - "checking" — spinner while the IPC round-trip is in flight
 * - "ok"       — green checkmark + "fully caught up" + dismiss
 * - "behind"   — list of upstream commits + link to GitHub compare view
 * - "error"    — surface the underlying git error (no upstream remote, etc.)
 *
 * Does NOT auto-merge. Surfaces what's available; merging is a deliberate
 * step the maintainer takes from the terminal because upstream changes can
 * touch agent prompts / decision parser / role definitions wrapped by
 * engine/live_debate.py.
 */

import { useEffect } from 'react';

import type { UpstreamCheckResult } from '../lib/upstream';
import styles from './UpstreamCheckModal.module.css';

export interface UpstreamCheckModalProps {
  /** "checking" while the check is in flight; a result object once it returns. */
  state: 'checking' | UpstreamCheckResult;
  onDismiss: () => void;
}

export function UpstreamCheckModal({ state, onDismiss }: UpstreamCheckModalProps): JSX.Element {
  // Esc dismisses. Always allowed — this is informational, not a gate.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onDismiss();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onDismiss]);

  if (state === 'checking') {
    return (
      <div className={styles.scrim} role="dialog" aria-modal="true">
        <div className={styles.modal}>
          <h2 className={styles.title}>Checking for updates…</h2>
          <p className={styles.body}>
            Fetching the latest commits from the upstream TradingAgents repository.
          </p>
          <div className={styles.spinner} />
        </div>
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className={styles.scrim} role="dialog" aria-modal="true">
        <div className={styles.modal}>
          <h2 className={`${styles.title} ${styles.titleError}`}>Update check failed</h2>
          <p className={styles.body}>{state.error}</p>
          <div className={styles.buttons}>
            <button type="button" className={styles.dismiss} onClick={onDismiss} autoFocus>
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (state.status === 'ok') {
    return (
      <div className={styles.scrim} role="dialog" aria-modal="true">
        <div className={styles.modal}>
          <h2 className={`${styles.title} ${styles.titleOk}`}>You're up to date</h2>
          <p className={styles.body}>
            Trading Agents Lab is current with upstream{' '}
            <code className={styles.code}>TauricResearch/TradingAgents</code>.
          </p>
          <dl className={styles.facts}>
            <div className={styles.factRow}>
              <dt>Latest tag</dt>
              <dd>{state.latestTag || '(none)'}</dd>
            </div>
            <div className={styles.factRow}>
              <dt>Upstream HEAD</dt>
              <dd><code className={styles.code}>{state.upstreamHead}</code></dd>
            </div>
            <div className={styles.factRow}>
              <dt>Our HEAD</dt>
              <dd><code className={styles.code}>{state.ourHead}</code></dd>
            </div>
            <div className={styles.factRow}>
              <dt>Our additions ahead</dt>
              <dd>{state.aheadCount} commits</dd>
            </div>
          </dl>
          <p className={styles.hint}>Checked {formatCheckedAt(state.checkedAt)}</p>
          <div className={styles.buttons}>
            <button type="button" className={styles.dismiss} onClick={onDismiss} autoFocus>
              OK
            </button>
          </div>
        </div>
      </div>
    );
  }

  // status === 'behind'
  return (
    <div className={styles.scrim} role="dialog" aria-modal="true">
      <div className={styles.modal}>
        <h2 className={`${styles.title} ${styles.titleWarn}`}>
          Updates available: {state.behindCount} commit{state.behindCount === 1 ? '' : 's'} behind
        </h2>
        <p className={styles.body}>
          Upstream <code className={styles.code}>TauricResearch/TradingAgents</code> has{' '}
          {state.behindCount} new commit{state.behindCount === 1 ? '' : 's'} not yet in your tree.
          Latest tag: <code className={styles.code}>{state.latestTag || '(none)'}</code>.
        </p>
        <ul className={styles.commitList}>
          {state.behindCommits.slice(0, 12).map((line, idx) => (
            <li key={idx} className={styles.commitItem}>
              <code className={styles.code}>{line}</code>
            </li>
          ))}
          {state.behindCommits.length > 12 && (
            <li className={styles.commitItem}>
              <em>… and {state.behindCommits.length - 12} more</em>
            </li>
          )}
        </ul>
        <p className={styles.hint}>
          Merging from the terminal is the next step (upstream changes can touch agent prompts /
          decision parser, manual review recommended):
        </p>
        <pre className={styles.codeBlock}>
{`git fetch upstream
git merge upstream/main
bash tools/dev-smoke.sh`}
        </pre>
        <div className={styles.buttons}>
          <button
            type="button"
            className={styles.dismiss}
            onClick={onDismiss}
          >
            Close
          </button>
          <button
            type="button"
            className={styles.primary}
            onClick={() => {
              window.open(state.compareUrl, '_blank', 'noopener,noreferrer');
            }}
            autoFocus
          >
            View on GitHub
          </button>
        </div>
      </div>
    </div>
  );
}

function formatCheckedAt(iso: string): string {
  try {
    const dt = new Date(iso);
    return `at ${dt.toLocaleTimeString()}`;
  } catch {
    return '';
  }
}
