/**
 * Renderer-side wrapper for the upstream-check IPC bridge.
 *
 * Triggers a `git fetch upstream` + comparison against TauricResearch's
 * TradingAgents (the codebase we forked from). Returns a structured result
 * the UI uses to render either a "Up to date" toast or a "X commits behind"
 * dialog with the upstream commit list.
 *
 * The check is user-initiated only — no background polling. Privacy:
 * one outbound network call to github.com via git's standard fetch
 * protocol; no telemetry or version pings to our own infrastructure.
 */

export interface UpstreamCheckResult {
  status: 'ok' | 'behind' | 'error';
  latestTag: string;
  upstreamHead: string;
  ourHead: string;
  behindCount: number;
  aheadCount: number;
  behindCommits: string[];
  checkedAt: string;
  error?: string;
  compareUrl: string;
}

export async function checkUpstream(): Promise<UpstreamCheckResult> {
  const bridge = window.tradingAgentsLab;
  if (!bridge?.checkUpstream) {
    throw new Error('upstream-check bridge not available: preload not loaded');
  }
  return bridge.checkUpstream();
}
