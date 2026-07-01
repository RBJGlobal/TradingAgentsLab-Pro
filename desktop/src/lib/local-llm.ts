/**
 * Local LLM helpers — config storage + credential resolution for the
 * `local` provider (Ollama / LM Studio / generic OpenAI-compat runtime).
 *
 * Why a dedicated module: the local provider's identity is the
 * (base_url, model) pair, NOT a single API key. The two values are
 * stored as separate safeStorage entries (`local:base-url`, `local:model`)
 * so they can be edited independently from Settings UI. Centralizing
 * here keeps the dual-secret coupling out of Analyze.tsx and Settings.tsx.
 *
 * The pair must be set together for the provider to be considered
 * configured — `isLocalConfigured()` checks both presence + non-empty.
 *
 * No native client lives in the renderer; the engine adapter is what
 * actually talks to localhost. The renderer just stores the user's
 * choice and ships it on the WS start frame as `auth: { type: 'local',
 * base_url }` + `model: <chosen-model>`.
 */

import {
  LOCAL_MODEL_SECRET_KEY,
  PROVIDER_SECRET_KEY,
} from './engine-client';
import { getSecret, setSecret } from './secrets';

const LOCAL_BASE_URL_KEY = PROVIDER_SECRET_KEY.local;

export interface LocalLLMConfig {
  /** OpenAI-compatible base URL — e.g. `http://localhost:11434/v1`. */
  base_url: string;
  /** Model id as the runtime returns it — e.g. `llama3.2:latest`. */
  model: string;
}

/**
 * Load the saved (base_url, model) pair. Returns null if either is
 * missing or empty — callers should treat that as "local not configured".
 *
 * Failures from safeStorage (e.g. encryption offline) bubble up; the
 * caller decides whether to swallow them (Settings) or treat them as a
 * hard fail (Analyze provider gate).
 */
export async function loadLocalConfig(): Promise<LocalLLMConfig | null> {
  const [baseUrl, model] = await Promise.all([
    getSecret(LOCAL_BASE_URL_KEY),
    getSecret(LOCAL_MODEL_SECRET_KEY),
  ]);
  if (!baseUrl || !model) return null;
  return { base_url: baseUrl, model };
}

/**
 * Persist the (base_url, model) pair atomically. We don't have a
 * true cross-entry transaction in safeStorage; if the second write
 * fails the user is left in a half-configured state. The Settings UI
 * surfaces save errors so they can retry. Order is base_url first so
 * a partial save leaves the more-informative half stored.
 */
export async function saveLocalConfig(config: LocalLLMConfig): Promise<void> {
  await setSecret(LOCAL_BASE_URL_KEY, config.base_url);
  await setSecret(LOCAL_MODEL_SECRET_KEY, config.model);
}

/**
 * Quick check used by the Analyze provider dropdown + StatusStrip LLM
 * pill to decide whether `local` should be selectable. Mirrors
 * `loadLocalConfig` but discards the value — the caller only needs
 * the boolean.
 */
export async function isLocalConfigured(): Promise<boolean> {
  const cfg = await loadLocalConfig();
  return cfg !== null;
}
