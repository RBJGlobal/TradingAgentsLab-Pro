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

import type { LLMProvider, ProConfig } from './engine-client';
import { migrateSavedModel } from './provider-models';

const STORAGE_KEY = 'tal:pro-config';

/** All four analyst nodes the full graph supports. All four run on free
 * sources by default (Yahoo Finance, plus Alpaca news when connected). An
 * Alpha Vantage key is optional and is used only when the user picks it as
 * the News or Fundamentals source below. */
export const ALL_ANALYSTS = ['market', 'social', 'news', 'fundamentals'] as const;
export type AnalystId = (typeof ALL_ANALYSTS)[number];

export const ANALYST_LABEL: Record<AnalystId, string> = {
  market: 'Market (technical)',
  social: 'Social sentiment',
  news: 'News',
  fundamentals: 'Fundamentals',
};


/** Anthropic reasoning-effort is the ONLY effort control we surface today,
 * and it applies to BOTH the deep and quick clients (the library threads
 * `anthropic_effort` into the shared llm_kwargs). Whether a model accepts it
 * is decided by `modelSupportsEffort`, which mirrors the vendored library's
 * rule (tradingagents/llm_clients/anthropic_client.py `_supports_effort`):
 * Opus 4.5+, Sonnet 4.6+, the Fable 5 family and later, plus a few exact
 * preview names. Sonnet 4.5 and every Haiku return HTTP 400. A rule (not a
 * fixed list) so models that arrive through the live model list are gated
 * correctly without a release. Effort is valid only when the provider is
 * Anthropic AND both the deep and the quick model accept it. */
const EFFORT_EXACT = new Set(['claude-mythos-preview', 'claude-mythos-5']);
const EFFORT_MODEL = /^claude-(opus|sonnet|fable)-(\d+)(?:-(\d+))?$/;
const EFFORT_MIN_VERSION: Record<string, [number, number]> = {
  opus: [4, 5],
  sonnet: [4, 6],
  fable: [5, 0],
};

/** True when Anthropic accepts the `effort` parameter for this model id.
 * Same regex, exact names and per-family minimums as the library, so the
 * renderer never sends effort the library would itself drop (or that would
 * 400). Dated snapshot ids do not match, same as the library. */
export function modelSupportsEffort(model: string): boolean {
  const id = model.toLowerCase();
  if (EFFORT_EXACT.has(id)) return true;
  const m = EFFORT_MODEL.exec(id);
  if (!m) return false;
  const [minMajor, minMinor] = EFFORT_MIN_VERSION[m[1]];
  const major = Number(m[2]);
  const minor = m[3] ? Number(m[3]) : 0;
  return major > minMajor || (major === minMajor && minor >= minMinor);
}

export const EFFORT_LEVELS = ['low', 'medium', 'high'] as const;
export type EffortLevel = (typeof EFFORT_LEVELS)[number];

/** Where the News analyst pulls headlines (Part B). `auto` prefers Alpaca's
 * Benzinga feed when Alpaca is connected (under Data Providers) and falls back
 * to Yahoo; `alpaca` forces Alpaca-first (still Yahoo fallback); `yfinance`
 * forces Yahoo only; `alpha_vantage` uses the user's Alpha Vantage key first
 * (opt-in). Yahoo stays the fallback whenever another source is in the chain,
 * so an empty or rate-limited primary never blanks the analyst. */
export const NEWS_SOURCES = ['auto', 'alpaca', 'yfinance', 'alpha_vantage'] as const;
export type NewsSource = (typeof NEWS_SOURCES)[number];

export const NEWS_SOURCE_LABEL: Record<NewsSource, string> = {
  auto: 'Auto (Alpaca when connected, else Yahoo)',
  alpaca: 'Alpaca (Benzinga)',
  yfinance: 'Yahoo Finance',
  alpha_vantage: 'Alpha Vantage (your key, Yahoo fallback)',
};

/** Where the Fundamentals analyst gets company data. `yfinance` is the free default; `alpha_vantage` is opt-in and uses the
 * user's key first, with Yahoo as the fallback (for example when the free
 * key's daily limit is reached). */
export const FUNDAMENTALS_SOURCES = ['yfinance', 'alpha_vantage'] as const;
export type FundamentalsSource = (typeof FUNDAMENTALS_SOURCES)[number];

export const FUNDAMENTALS_SOURCE_LABEL: Record<FundamentalsSource, string> = {
  yfinance: 'Yahoo Finance',
  alpha_vantage: 'Alpha Vantage (your key, Yahoo fallback)',
};

/** How a Pro run is analyzed (Pro 1.1.10+).
 *
 * - `full`: the real LangGraph graph (analyst team with tools, bull/bear
 *   research debate, trader, risk team, portfolio manager), deep/quick
 *   model split, Pro Cost Guard estimate.
 * - `quick`: the Lite app's simplified debate on the engine's live_debate
 *   path: twelve agents on the one selected model, a single pass, the
 *   simplified Cost Guard estimate. The analyst / round / effort / token cap
 *   settings below do not apply to it.
 */
export const RUN_MODES = ['full', 'quick'] as const;
export type RunMode = (typeof RUN_MODES)[number];

export const RUN_MODE_LABEL: Record<RunMode, string> = {
  full: 'Full analysis',
  quick: 'Quick analysis',
};

/** Which analysis produced a row: 'Full' (LangGraph graph) or 'Quick'
 * (Quick analysis or a Telegram bot run). Rows saved before Pro 1.1.10 have
 * no mode and show none. */
export function runModeTag(mode: string | null | undefined): string {
  if (mode === 'quick') return 'Quick · ';
  if (mode === 'full') return 'Full · ';
  return '';
}

export interface ProConfigState {
  /** Full graph or Quick analysis. Default `full` (the Pro behavior before
   * run modes existed). */
  runMode: RunMode;
  /** null = use the primary model the user picked on Analyze (the deep model). */
  deepModel: string | null;
  quickModel: string | null;
  effort: EffortLevel | null;
  maxDebateRounds: number;
  maxRiskRounds: number;
  selectedAnalysts: AnalystId[];
  /** News analyst headline source (Part B). Default `auto`. */
  newsSource: NewsSource;
  /** Fundamentals source. Default `yfinance`. */
  fundamentalsSource: FundamentalsSource;
  /** Hard token-cap backstop; null = no cap (rely on the pre-flight reserve). */
  tokenCap: number | null;
}

export const DEFAULT_PRO_CONFIG: ProConfigState = {
  runMode: 'full',
  deepModel: null,
  quickModel: null,
  effort: null,
  maxDebateRounds: 1,
  maxRiskRounds: 1,
  selectedAnalysts: ['market'],
  newsSource: 'auto',
  fundamentalsSource: 'yfinance',
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
    // Coerce to a known source so a corrupt/older blob can't send a bad value.
    const newsSource = (NEWS_SOURCES as readonly string[]).includes(parsed.newsSource as string)
      ? (parsed.newsSource as NewsSource)
      : DEFAULT_PRO_CONFIG.newsSource;
    const fundamentalsSource = (FUNDAMENTALS_SOURCES as readonly string[]).includes(
      parsed.fundamentalsSource as string,
    )
      ? (parsed.fundamentalsSource as FundamentalsSource)
      : DEFAULT_PRO_CONFIG.fundamentalsSource;
    const runMode = (RUN_MODES as readonly string[]).includes(parsed.runMode as string)
      ? (parsed.runMode as RunMode)
      : DEFAULT_PRO_CONFIG.runMode;
    return {
      ...DEFAULT_PRO_CONFIG,
      ...parsed,
      // Never allow an empty analyst set (a run with zero analysts is invalid).
      selectedAnalysts: analysts.length > 0 ? analysts : DEFAULT_PRO_CONFIG.selectedAnalysts,
      newsSource,
      fundamentalsSource,
      runMode,
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
 * See modelSupportsEffort: guards the both-models-accept-it requirement so
 * we never ship a request that 400s on the quick client. */
export function effortAllowed(
  provider: string | null,
  deepModel: string,
  quickModel: string,
): boolean {
  return (
    provider === 'anthropic' &&
    modelSupportsEffort(deepModel) &&
    modelSupportsEffort(quickModel)
  );
}

/** Providers whose saved model ids may need a one-time remap. */
const KNOWN_PROVIDERS: readonly LLMProvider[] = [
  'openai', 'anthropic', 'openrouter', 'gemini', 'xai', 'minimax', 'local',
];

/** Apply the same retired-id remap Analyze applies to the primary model
 * (provider-models.ts `migrateSavedModel`) to a saved deep/quick override,
 * so a saved `gemini-2.0-flash` runs as `gemini-3.1-flash-lite` instead of
 * failing. null stays null ("use the primary model"). */
export function migrateSavedRoleModel(
  provider: string | null,
  saved: string | null,
): string | null {
  if (!saved || !provider) return saved;
  if (!(KNOWN_PROVIDERS as readonly string[]).includes(provider)) return saved;
  return migrateSavedModel(provider as LLMProvider, saved);
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
  const deep = migrateSavedRoleModel(provider, state.deepModel) || primaryModel;
  const quick = migrateSavedRoleModel(provider, state.quickModel) || primaryModel;
  const cfg: ProConfig = {
    deep_think_llm: deep,
    quick_think_llm: quick,
    max_debate_rounds: state.maxDebateRounds,
    max_risk_discuss_rounds: state.maxRiskRounds,
    selected_analysts: state.selectedAnalysts.slice(),
    news_source: state.newsSource,
    fundamentals_source: state.fundamentalsSource,
  };
  if (state.tokenCap && state.tokenCap > 0) {
    cfg.token_cap = state.tokenCap;
  }
  if (state.effort && effortAllowed(provider, deep, quick)) {
    cfg.effort = state.effort;
  }
  return cfg;
}
