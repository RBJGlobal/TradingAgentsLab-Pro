/**
 * Renderer-side wrapper for the OpenAI OAuth bridge exposed by preload.
 *
 * The renderer never holds the access/refresh tokens longer than necessary —
 * `getOpenAICredentialsForRequest()` is called just before building the WS
 * start frame, attaches the access token, and returns. Tokens never live in
 * React state.
 */

import { OAUTH_ENABLED } from './feature-flags';

export interface OAuthStartResult {
  success: boolean;
  email?: string;
  error?: string;
}

export interface OAuthStatus {
  connected: boolean;
  email?: string;
  expiresAt?: number;
  needsRefresh?: boolean;
  /** ChatGPT plan tier from the OAuth JWT — `"free"`, `"plus"`, `"pro"`,
   * `"team"`, `"enterprise"`, etc. `undefined` when JWT decode failed. */
  planType?: string;
  /** True when `planType === "free"`. Codex routing is unreliable on
   * free-tier accounts; UI surfaces a banner. */
  isFreeTier?: boolean;
}

export interface OAuthProgressEvent { message: string }
export interface OAuthPromptEvent { message: string; placeholder?: string }

export interface OAuthCredentials {
  access: string;
  refresh: string;
  expires: number;
  email?: string;
  /** Required for the Codex backend's `chatgpt-account-id` header. */
  accountId?: string;
}

function bridge() {
  if (!window.tradingAgentsLab?.oauth) {
    throw new Error('oauth bridge not available: preload not loaded');
  }
  return window.tradingAgentsLab.oauth;
}

export function startOpenAIOAuthLogin(): Promise<OAuthStartResult> {
  return bridge().openaiStart();
}

export function getOpenAIOAuthStatus(): Promise<OAuthStatus> {
  // With OAuth hidden in Pro v1, report disconnected unconditionally so
  // stale vault tokens from earlier builds never outrank an API key in
  // provider resolution (Analyze / BatchRunner treat OAuth as absent).
  if (!OAUTH_ENABLED) return Promise.resolve({ connected: false });
  return bridge().openaiStatus();
}

export function disconnectOpenAIOAuth(): Promise<boolean> {
  return bridge().openaiDisconnect();
}

export function submitOAuthPromptResponse(value: string): void {
  bridge().openaiPromptResponse(value);
}

/**
 * Fetch fresh credentials from the main process. The main-process service
 * silently refreshes if the cached access token is within a 60s window of
 * expiry. Used by `Analyze.tsx` immediately before calling `streamDebate`.
 */
export function getOpenAICredentialsForRequest(): Promise<OAuthCredentials | null> {
  return bridge().openaiCredentials();
}

export function onOAuthProgress(
  handler: (event: OAuthProgressEvent) => void,
): () => void {
  return bridge().onProgress(handler);
}

export function onOAuthPrompt(
  handler: (event: OAuthPromptEvent) => void,
): () => void {
  return bridge().onPrompt(handler);
}
