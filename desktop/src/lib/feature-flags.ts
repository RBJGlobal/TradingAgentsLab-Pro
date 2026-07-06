/**
 * Build-time feature flags for Pro.
 *
 * OAUTH_ENABLED — OpenAI OAuth (ChatGPT-plan sign-in) is hidden in Pro v1.
 * The Codex /responses adapter behind it is text-only (no tool-calling), and
 * the real LangGraph debate is tool-heavy, so an OAuth-driven run silently
 * degrades below the quality the user paid for. While this is false:
 *   - Settings hides the OAuth row (Settings.tsx),
 *   - getOpenAIOAuthStatus() reports disconnected everywhere, so stale
 *     vault tokens from earlier builds can never win the provider
 *     resolution over an API key (Analyze.tsx / BatchRunner.tsx).
 * Flip to true in v1.1 once the Codex adapter supports tool-calling and is
 * wrapped as a LangChain BaseChatModel (see Pro backlog).
 */
export const OAUTH_ENABLED = false;
