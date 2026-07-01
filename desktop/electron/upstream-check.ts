/**
 * Upstream-update check for TradingAgentsLab.
 *
 * Mirrors `tools/upstream-check.sh` but runs from the Electron main process
 * via Node's child_process so the renderer can trigger it via IPC and show
 * results in the UI. No shell — direct git invocation, no command injection
 * surface.
 *
 * Returns a structured result the renderer can render either as a dialog
 * (when behind) or as a quiet "up to date" toast.
 *
 * Privacy note: this performs a `git fetch upstream`. That's the only
 * outbound network call. No data leaves the machine other than git's
 * standard fetch protocol to github.com (the upstream remote URL). No
 * telemetry, no version pings to our own infrastructure (we don't have
 * any) — see project_risk_profile_and_education.md.
 */

import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { app } from 'electron';
import path from 'node:path';

const execFileAsync = promisify(execFile);

const REPO_URL = 'https://github.com/TauricResearch/TradingAgents';

export interface UpstreamCheckResult {
  /** Either "ok" (caught up) or "behind" (commits available). "error" on
   * failure (no upstream remote, network issue, no git binary, etc.). */
  status: 'ok' | 'behind' | 'error';
  /** Latest tag on upstream/main. May be empty if upstream has no tags. */
  latestTag: string;
  /** Short SHA of upstream/main HEAD. */
  upstreamHead: string;
  /** Short SHA of our local main HEAD. */
  ourHead: string;
  /** How many commits we are behind upstream/main. 0 when caught up. */
  behindCount: number;
  /** How many commits we are ahead of upstream/main (our additions). */
  aheadCount: number;
  /** Commit one-liners for each commit on upstream/main not in our main.
   * Format: "abc1234 message". Empty when behindCount=0. */
  behindCommits: string[];
  /** ISO-8601 UTC timestamp of when this check ran. */
  checkedAt: string;
  /** Error message when status === "error". */
  error?: string;
  /** Public URL the user can visit to see the upstream commits diff. */
  compareUrl: string;
}

function repoRoot(): string {
  // app.getAppPath() in dev is <repo>/desktop. In production builds the path
  // shape may differ — fall back to one level up regardless.
  return path.resolve(app.getAppPath(), '..');
}

async function git(args: string[]): Promise<string> {
  const { stdout } = await execFileAsync('git', args, {
    cwd: repoRoot(),
    timeout: 30_000,
    env: process.env,
  });
  return stdout.trim();
}

export async function checkUpstream(): Promise<UpstreamCheckResult> {
  const checkedAt = new Date().toISOString();
  const baseResult: UpstreamCheckResult = {
    status: 'error',
    latestTag: '',
    upstreamHead: '',
    ourHead: '',
    behindCount: 0,
    aheadCount: 0,
    behindCommits: [],
    checkedAt,
    compareUrl: REPO_URL,
  };

  try {
    // Verify upstream remote exists. Throws if missing.
    await git(['remote', 'get-url', 'upstream']);
  } catch (exc) {
    return {
      ...baseResult,
      error:
        'No `upstream` git remote configured. Run: ' +
        '`git remote add upstream https://github.com/TauricResearch/TradingAgents.git`',
    };
  }

  try {
    // Fetch latest from upstream — this is the only outbound network call.
    await git(['fetch', 'upstream', '--tags', '--quiet']);
  } catch (exc) {
    const msg = exc instanceof Error ? exc.message : String(exc);
    return {
      ...baseResult,
      error: `Fetch from upstream failed: ${msg}`,
    };
  }

  try {
    const [latestTag, upstreamHead, ourHead, behindCount, aheadCount] =
      await Promise.all([
        git(['tag', '-l', '--sort=-version:refname', '--merged', 'upstream/main'])
          .then((s) => s.split('\n')[0]?.trim() ?? '')
          .catch(() => ''),
        git(['rev-parse', '--short', 'upstream/main']),
        git(['rev-parse', '--short', 'main']),
        git(['rev-list', 'main..upstream/main', '--count']).then((s) => parseInt(s, 10) || 0),
        git(['rev-list', 'upstream/main..main', '--count']).then((s) => parseInt(s, 10) || 0),
      ]);

    let behindCommits: string[] = [];
    if (behindCount > 0) {
      const log = await git(['log', 'main..upstream/main', '--oneline', '--no-decorate']);
      behindCommits = log.split('\n').filter((l) => l.trim().length > 0);
    }

    return {
      status: behindCount > 0 ? 'behind' : 'ok',
      latestTag,
      upstreamHead,
      ourHead,
      behindCount,
      aheadCount,
      behindCommits,
      checkedAt,
      compareUrl:
        behindCount > 0
          ? `${REPO_URL}/compare/${ourHead}...${upstreamHead}`
          : REPO_URL,
    };
  } catch (exc) {
    const msg = exc instanceof Error ? exc.message : String(exc);
    return {
      ...baseResult,
      error: `Git comparison failed: ${msg}`,
    };
  }
}
