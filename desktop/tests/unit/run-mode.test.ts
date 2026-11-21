// @vitest-environment happy-dom
//
// Pro 1.1.10 run modes. Full analysis drives the LangGraph graph (engine
// 'pro' + pro_config + the Pro Cost Guard estimate); Quick analysis drives
// the Lite-style debate (engine 'quick', no pro_config, the simplified
// estimate, i.e. a reserve request with no `pro` block).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const streamDebate = vi.fn();
const reserveCostGuard = vi.fn();
const listProviderModels = vi.fn();
const order: string[] = [];

vi.mock('../../src/lib/engine-client', async (orig) => ({
  ...(await orig<typeof import('../../src/lib/engine-client')>()),
  streamDebate: (...a: unknown[]) => streamDebate(...a),
  listProviderModels: (...a: unknown[]) => { order.push('catalog'); return listProviderModels(...a); },
}));
vi.mock('../../src/lib/cost-guard', async (orig) => ({
  ...(await orig<typeof import('../../src/lib/cost-guard')>()),
  reserveCostGuard: (...a: unknown[]) => { order.push('reserve'); return reserveCostGuard(...a); },
}));
vi.mock('../../src/lib/secrets', () => ({
  getSecret: async (name: string) =>
    name === 'llm:anthropic' ? 'sk-ant-test' : name === 'llm:openrouter' ? 'sk-or-test' : null,
}));
vi.mock('../../src/lib/webhooks', () => ({ loadWebhooks: async () => [] }));

import { runAnalysis } from '../../src/lib/run-analysis';
import {
  DEFAULT_PRO_CONFIG,
  loadProConfig,
  runModeTag,
  saveProConfig,
} from '../../src/lib/pro-config';

beforeEach(() => {
  streamDebate.mockReset().mockResolvedValue({ close: () => {}, done: Promise.resolve() });
  reserveCostGuard.mockReset().mockResolvedValue({ reservation_id: 'r1' });
  listProviderModels.mockReset().mockResolvedValue({ ok: true, models: [] });
  order.length = 0;
});
afterEach(() => localStorage.clear());

async function run() {
  await runAnalysis(
    {
      ticker: 'NVDA',
      trade_date: '2026-11-20',
      provider: 'anthropic',
      openaiAuthKind: 'api_key',
      model: 'claude-sonnet-5-5',
    },
    { onEvent: () => {} },
  );
  return { reserve: reserveCostGuard.mock.calls[0][0], start: streamDebate.mock.calls[0][0] };
}

describe('run mode setting', () => {
  it('defaults to full and survives a corrupt or older blob', () => {
    expect(loadProConfig().runMode).toBe('full');
    localStorage.setItem('tal:pro-config', JSON.stringify({ runMode: 'turbo' }));
    expect(loadProConfig().runMode).toBe('full');
    saveProConfig({ ...DEFAULT_PRO_CONFIG, runMode: 'quick' });
    expect(loadProConfig().runMode).toBe('quick');
  });

  it('tags History rows by mode, and leaves pre-1.1.10 rows untagged', () => {
    expect(runModeTag('quick')).toBe('Quick · ');
    expect(runModeTag('full')).toBe('Full · ');
    expect(runModeTag(null)).toBe('');
    expect(runModeTag(undefined)).toBe('');
  });
});

describe('runAnalysis by mode', () => {
  it('full: engine pro, pro_config, Pro estimate', async () => {
    saveProConfig({ ...DEFAULT_PRO_CONFIG, runMode: 'full' });
    const { reserve, start } = await run();
    expect(start.engine).toBe('pro');
    expect(start.pro_config.deep_think_llm).toBe('claude-sonnet-5-5');
    expect(reserve.pro).toBeDefined();
  });

  it('quick: engine quick, no pro_config, simplified estimate on the picked model', async () => {
    saveProConfig({
      ...DEFAULT_PRO_CONFIG,
      runMode: 'quick',
      // Full-only knobs must not leak into a Quick run.
      deepModel: 'claude-opus-5-5',
      selectedAnalysts: ['market', 'news'],
    });
    const { reserve, start } = await run();
    expect(start.engine).toBe('quick');
    expect(start.pro_config).toBeUndefined();
    expect(start.alpha_vantage_key).toBeUndefined();
    expect(start.provider_config.model).toBe('claude-sonnet-5-5');
    expect(reserve).toEqual({
      model: 'claude-sonnet-5-5',
      auth_kind: 'api_key',
      max_tokens: 400,
      provider: 'anthropic',
    });
  });
});

describe('OpenRouter catalog before the reservation', () => {
  it('loads the catalog first so reserve and run see the same reasoning flags', async () => {
    saveProConfig({ ...DEFAULT_PRO_CONFIG, runMode: 'quick' });
    await runAnalysis(
      { ticker: 'NVDA', trade_date: '2026-11-20', provider: 'openrouter',
        openaiAuthKind: 'api_key', model: 'deepseek/deepseek-v4' },
      { onEvent: () => {} },
    );
    expect(order).toEqual(['catalog', 'reserve']);
  });

  it('a failed catalog fetch never blocks the run', async () => {
    listProviderModels.mockRejectedValue(new Error('offline'));
    await runAnalysis(
      { ticker: 'NVDA', trade_date: '2026-11-20', provider: 'openrouter',
        openaiAuthKind: 'api_key', model: 'deepseek/deepseek-v4' },
      { onEvent: () => {} },
    );
    expect(reserveCostGuard).toHaveBeenCalledOnce();
  });

  it('other providers skip it', async () => {
    await run();
    expect(order).toEqual(['reserve']);
  });
});
