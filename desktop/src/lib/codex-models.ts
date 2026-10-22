/**
 * Live model list for the OpenAI OAuth (Codex / ChatGPT-account) picker.
 *
 * OpenAI retires ChatGPT-sign-in models on its own schedule (the whole
 * gpt-5.x line was retired in 2026), so the picker must reflect what the
 * signed-in account can use TODAY rather than a list baked into the build.
 * This hook asks the engine (POST /llm/models -> OpenAI's Codex catalog) and
 * keeps the last good live list in localStorage so the picker is correct
 * instantly on the next launch, before the refetch lands.
 *
 * Order: cached live list (if any) -> built-in fallback, then replaced by the
 * fresh live list when it arrives. The first entry is marked recommended so
 * Analyze's existing "saved choice not in list -> use recommended" rule
 * automatically moves anyone off a retired model.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  listCodexModels,
  OPENAI_CODEX_MODELS,
  type ModelChoice,
  type ProviderConfig,
} from './engine-client';
import { getOpenAICredentialsForRequest } from './oauth';

const CACHE_KEY = 'tal:codex-models:v1';

export type CodexModelsSource = 'live' | 'cached' | 'fallback';

function withRecommended(models: ModelChoice[]): ModelChoice[] {
  return models.map((m, i) => ({ ...m, recommended: i === 0 }));
}

function readCache(): ModelChoice[] | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed) || parsed.length === 0) return null;
    const ok = parsed.every(
      (m) => m && typeof m === 'object' && typeof (m as ModelChoice).id === 'string',
    );
    return ok ? (parsed as ModelChoice[]) : null;
  } catch {
    return null;
  }
}

function writeCache(models: ModelChoice[]): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(models));
  } catch {
    /* storage unavailable: non-fatal, we just refetch next launch */
  }
}

/** Build the same OAuth provider_config shape live runs send. */
async function oauthProviderConfig(): Promise<ProviderConfig | null> {
  const creds = await getOpenAICredentialsForRequest();
  if (!creds) return null;
  return {
    provider: 'openai',
    auth: {
      type: 'oauth',
      access: creds.access,
      refresh: creds.refresh,
      expires: creds.expires,
      account_id: creds.accountId,
    },
  };
}

export interface CodexModelsState {
  models: ModelChoice[];
  source: CodexModelsSource;
  loading: boolean;
  /** Re-query OpenAI's catalog, bypassing the engine's 15-minute cache. */
  refresh: () => void;
}

/**
 * @param enabled only fetch when the active provider is OpenAI via OAuth;
 *   when false the hook is inert and returns the cached/fallback list.
 */
export function useCodexModels(enabled: boolean): CodexModelsState {
  const [models, setModels] = useState<ModelChoice[]>(() =>
    withRecommended(readCache() ?? OPENAI_CODEX_MODELS),
  );
  const [source, setSource] = useState<CodexModelsSource>(() =>
    readCache() ? 'cached' : 'fallback',
  );
  const [loading, setLoading] = useState(false);
  const [nonce, setNonce] = useState(0);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const cfg = await oauthProviderConfig();
        if (!cfg || cancelled) return;
        const res = await listCodexModels(cfg, nonce > 0);
        if (cancelled || !res.ok || !res.models || res.models.length === 0) return;
        const next = withRecommended(res.models);
        setModels(next);
        setSource(res.source === 'live' ? 'live' : 'fallback');
        if (res.source === 'live') writeCache(next);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled, nonce]);

  return { models, source, loading, refresh };
}
