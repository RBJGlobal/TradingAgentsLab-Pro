/**
 * Build-time feature flags for Pro.
 *
 * OAUTH_ENABLED — OpenAI OAuth (ChatGPT-plan sign-in) drives the REAL
 * LangGraph graph on this branch: the engine routes provider="openai"
 * LLM construction through the Codex subscription backend, which speaks
 * the same Responses API wire shape the library already uses — including
 * tool-calling (verified by live spike, 2026-07-05; see
 * engine/codex_llm.py). While this is false the OAuth row is hidden and
 * getOpenAIOAuthStatus() reports disconnected everywhere, so vault
 * tokens can never win provider resolution over an API key.
 */
export const OAUTH_ENABLED = true;
