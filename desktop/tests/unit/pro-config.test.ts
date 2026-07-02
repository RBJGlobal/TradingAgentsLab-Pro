// @vitest-environment happy-dom
//
// Unit tests for the Pro run-config assembly + the Anthropic effort guard.
// These are the pure decisions behind every Pro run (engine='pro' path), so
// they must be correct independent of the UI: the deep/quick split defaulting,
// the both-models effort guard (only claude-sonnet-4-6 accepts effort, and it
// hits BOTH clients), token-cap inclusion, and corrupt-blob load recovery.
import { afterEach, describe, expect, it } from 'vitest';
import {
  assembleProConfig,
  effortAllowed,
  loadProConfig,
  saveProConfig,
  DEFAULT_PRO_CONFIG,
  type ProConfigState,
} from '../../src/lib/pro-config';

afterEach(() => localStorage.clear());

const base: ProConfigState = { ...DEFAULT_PRO_CONFIG };

describe('assembleProConfig', () => {
  it('defaults deep and quick to the primary model, single-analyst market run', () => {
    const cfg = assembleProConfig('claude-sonnet-4-6', 'anthropic', base);
    expect(cfg.deep_think_llm).toBe('claude-sonnet-4-6');
    expect(cfg.quick_think_llm).toBe('claude-sonnet-4-6');
    expect(cfg.max_debate_rounds).toBe(1);
    expect(cfg.max_risk_discuss_rounds).toBe(1);
    expect(cfg.selected_analysts).toEqual(['market']);
    expect(cfg.token_cap).toBeUndefined();
    // effort is null in defaults -> never sent
    expect(cfg.effort).toBeUndefined();
  });

  it('honours an explicit deep/quick split', () => {
    const cfg = assembleProConfig('claude-sonnet-4-6', 'anthropic', {
      ...base,
      deepModel: 'claude-opus-4-7',
      quickModel: 'claude-haiku-4-5',
    });
    expect(cfg.deep_think_llm).toBe('claude-opus-4-7');
    expect(cfg.quick_think_llm).toBe('claude-haiku-4-5');
  });

  it('includes token_cap only when positive', () => {
    expect(assembleProConfig('m', 'anthropic', { ...base, tokenCap: 0 }).token_cap).toBeUndefined();
    expect(assembleProConfig('m', 'anthropic', { ...base, tokenCap: 200000 }).token_cap).toBe(200000);
  });

  it('sends effort ONLY when provider is anthropic and BOTH models accept it', () => {
    // both sonnet-4-6 -> allowed
    const ok = assembleProConfig('claude-sonnet-4-6', 'anthropic', {
      ...base,
      effort: 'high',
    });
    expect(ok.effort).toBe('high');

    // quick model is haiku (400s on effort) -> guard drops it
    const splitBad = assembleProConfig('claude-sonnet-4-6', 'anthropic', {
      ...base,
      effort: 'high',
      quickModel: 'claude-haiku-4-5',
    });
    expect(splitBad.effort).toBeUndefined();

    // non-anthropic provider -> no anthropic effort
    const openai = assembleProConfig('gpt-5.5', 'openai', { ...base, effort: 'high' });
    expect(openai.effort).toBeUndefined();
  });
});

describe('effortAllowed', () => {
  it('requires anthropic + both models effort-capable', () => {
    expect(effortAllowed('anthropic', 'claude-sonnet-4-6', 'claude-sonnet-4-6')).toBe(true);
    expect(effortAllowed('anthropic', 'claude-sonnet-4-6', 'claude-sonnet-4-5')).toBe(false);
    expect(effortAllowed('anthropic', 'claude-haiku-4-5', 'claude-sonnet-4-6')).toBe(false);
    expect(effortAllowed('openai', 'claude-sonnet-4-6', 'claude-sonnet-4-6')).toBe(false);
    expect(effortAllowed(null, 'claude-sonnet-4-6', 'claude-sonnet-4-6')).toBe(false);
  });
});

describe('loadProConfig recovery', () => {
  it('round-trips a saved config', () => {
    const custom: ProConfigState = {
      ...base,
      maxDebateRounds: 2,
      selectedAnalysts: ['market', 'news'],
      tokenCap: 150000,
    };
    saveProConfig(custom);
    expect(loadProConfig()).toEqual(custom);
  });

  it('falls back to defaults on a corrupt blob', () => {
    localStorage.setItem('tal:pro-config', '{not json');
    expect(loadProConfig()).toEqual(DEFAULT_PRO_CONFIG);
  });

  it('never yields an empty analyst set (invalid run)', () => {
    saveProConfig({ ...base, selectedAnalysts: [] });
    expect(loadProConfig().selectedAnalysts).toEqual(['market']);
  });

  it('drops unknown analyst ids from a stale blob', () => {
    localStorage.setItem(
      'tal:pro-config',
      JSON.stringify({ ...base, selectedAnalysts: ['market', 'bogus'] }),
    );
    expect(loadProConfig().selectedAnalysts).toEqual(['market']);
  });
});
