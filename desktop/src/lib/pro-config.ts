/**
 * Pro-only run configuration (Trading Agents Lab Pro).
 *
 * The Pro app is a distinct build that ALWAYS drives the real LangGraph
 * "full" engine (see `engine: 'pro'` in run-analysis.ts). These are the
 * knobs that engine exposes beyond the free app's single-model pick: the
 * deep/quick model split, reasoning effort, debate round counts, which
 * analysts run, and a hard token-cap backstop.
 *
 * Persistence mirrors the free app's per-provider model choice: a small
 * localStorage blob, read at run-assembly time. Defaults are deliberately
 * conservative and key-free: analysts = ['market'] runs on yfinance alone
 * (no Alpha Vantage key needed), so a fresh Pro install produces a working
 * full-graph run before the user configures anything or adds a data key.
 */

import type { ProConfig } from './engine-client';

const STORAGE_KEY = 'tal:pro-config';

/** All four analyst nodes the full graph supports. Only `market` is
 * key-free (yfinance); `social`/`news`/`fundamentals` route through Alpha
 * Vantage and need a data key (surfaced in Settings as a fast-follow). */
export const ALL_ANALYSTS = ['market', 'social', 'news', 'fundamentals'] as const;
export type AnalystId = (typeof ALL_ANALYSTS)[number];

export const ANALYST_LABEL: Record<AnalystId, string> = {
  market: 'Market (technical)',
  social: 'Social sentiment',
  news: 'News',
  fundamentals: 'Fundamentals',
};

/** Analysts that require an Alpha Vantage data key. `market` is free. */
export const ANALYSTS_NEEDING_DATA_KEY: AnalystId[] = ['social', 'news', 'fundamentals'];

/** Anthropic reasoning-effort is the ONLY effort control we surface today,
 * and it applies to BOTH the deep and quick clients (the library threads
 * `anthropic_effort` into the shared llm_kwargs). Only claude-sonnet-4-6
 * accepts the param; haiku-4-5 and sonnet-4-5 return HTTP 400. So effort is
 * valid only when the provider is Anthropic AND both models are the one
 * effort-capable model. */
export const EFFORT_CAPABLE_MODELS = new Set(['claude-sonnet-4-6']);
export const EFFORT_LEVELS = ['low', 'medium', 'high'] as const;
export type EffortLevel = (typeof EFFORT_LEVELS)[number];

export interface ProConfigState {
  /** null = use the primary model the user picked on Analyze (the deep model). */
  deepModel: string | null;
  quickModel: string | null;
  effort: EffortLevel | null;
  maxDebateRounds: number;
  maxRiskRounds: number;
  selectedAnalysts: AnalystId[];
  /** Hard token-cap backstop; null = no cap (rely on the pre-flight reserve). */
  tokenCap: number | null;
}

export const DEFAULT_PRO_CONFIG: ProConfigState = {
  deepModel: null,
  quickModel: null,
  effort: null,
  maxDebateRounds: 1,
  maxRiskRounds: 1,
  selectedAnalysts: ['market'],
  tokenCap: null,
};

export function loadProConfig(): ProConfigState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PRO_CONFIG };
    const parsed = JSON.parse(raw) as Partial<ProConfigState>;
    // Merge over defaults so a stored blob from an older shape can't drop a
    // field, and coerce the analyst list to known ids (guards a corrupt blob).
    const analysts = Array.isArray(parsed.selectedAnalysts)
      ? parsed.selectedAnalysts.filter((a): a is AnalystId =>
          (ALL_ANALYSTS as readonly string[]).includes(a),
        )
      : DEFAULT_PRO_CONFIG.selectedAnalysts;
    return {
      ...DEFAULT_PRO_CONFIG,
      ...parsed,
      // Never allow an empty analyst set (a run with zero analysts is invalid).
      selectedAnalysts: analysts.length > 0 ? analysts : DEFAULT_PRO_CONFIG.selectedAnalysts,
    };
  } catch {
    return { ...DEFAULT_PRO_CONFIG };
  }
}

export function saveProConfig(state: ProConfigState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* storage full / unavailable — non-fatal, run uses in-memory state */
  }
}

/** True when Anthropic reasoning-effort may be sent for this deep/quick pair.
 * See EFFORT_CAPABLE_MODELS: guards the both-models-accept-it requirement so
 * we never ship a request that 400s on the quick client. */
export function effortAllowed(
  provider: string | null,
  deepModel: string,
  quickModel: string,
): boolean {
  return (
    provider === 'anthropic' &&
    EFFORT_CAPABLE_MODELS.has(deepModel) &&
    EFFORT_CAPABLE_MODELS.has(quickModel)
  );
}

/**
 * Build the wire `pro_config` from the stored state + the primary model the
 * caller resolved (the deep model). Pure so it can be unit-tested without
 * localStorage. `provider` gates the effort field.
 */
export function assembleProConfig(
  primaryModel: string,
  provider: string | null,
  state: ProConfigState = loadProConfig(),
): ProConfig {
  const deep = state.deepModel || primaryModel;
  const quick = state.quickModel || primaryModel;
  const cfg: ProConfig = {
    deep_think_llm: deep,
    quick_think_llm: quick,
    max_debate_rounds: state.maxDebateRounds,
    max_risk_discuss_rounds: state.maxRiskRounds,
    selected_analysts: state.selectedAnalysts.slice(),
  };
  if (state.tokenCap && state.tokenCap > 0) {
    cfg.token_cap = state.tokenCap;
  }
  if (state.effort && effortAllowed(provider, deep, quick)) {
    cfg.effort = state.effort;
  }
  return cfg;
}
