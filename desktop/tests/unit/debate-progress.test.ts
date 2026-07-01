// Unit tests for DebateStream's dual-mode progress model (P2 / Pro).
//
// The free engine emits no graph.plan, so totals fall back to the fixed
// 4/3/1/4 roster. The Pro full-graph engine emits graph.plan and the
// researcher/risk totals scale with the round counts. rounds=1 is already
// confirmed by a live run; these tests lock the rounds>1 extrapolation, the
// free fallback, analyst-selection, activity marking, and that terminal
// events never inflate progress.
import { describe, expect, it } from 'vitest';
import { computeProgress, derivePhaseTotals } from '../../src/components/DebateStream';
import type { DebateEvent } from '../../src/lib/engine-client';

const msg = (agent: string, phase: string, round?: number): DebateEvent =>
  ({ type: 'agent.message', agent, phase, content: 'x', round } as DebateEvent);

const plan = (
  analysts: string[],
  max_debate_rounds: number,
  max_risk_rounds: number,
): DebateEvent =>
  ({ type: 'graph.plan', analysts, max_debate_rounds, max_risk_rounds } as DebateEvent);

const ALL_ANALYSTS = ['market', 'social', 'news', 'fundamentals'];

describe('derivePhaseTotals', () => {
  it('falls back to the fixed 4/3/1/4 roster with no graph.plan (free engine)', () => {
    const { totals, totalAgents } = derivePhaseTotals([msg('a', 'analysts')]);
    expect(totals).toEqual({ analysts: 4, researchers: 3, trader: 1, risk: 4 });
    expect(totalAgents).toBe(12);
  });

  it('derives rounds=1 totals from graph.plan (matches the live Pro run)', () => {
    const { totals, totalAgents } = derivePhaseTotals([plan(ALL_ANALYSTS, 1, 1)]);
    expect(totals).toEqual({ analysts: 4, researchers: 3, trader: 1, risk: 4 });
    expect(totalAgents).toBe(12);
  });

  it('scales researcher/risk totals with rounds=2', () => {
    const { totals, totalAgents } = derivePhaseTotals([plan(ALL_ANALYSTS, 2, 2)]);
    // researchers = 2*2+1 = 5 (bull+bear per round, then manager)
    // risk = 3*2+1 = 7 (aggressive+conservative+neutral per round, then PM)
    expect(totals).toEqual({ analysts: 4, researchers: 5, trader: 1, risk: 7 });
    expect(totalAgents).toBe(17);
  });

  it('uses the selected-analyst count for the analysts total', () => {
    const { totals } = derivePhaseTotals([plan(['market'], 1, 1)]);
    expect(totals.analysts).toBe(1);
  });

  it('degrades to fixed totals when graph.plan fields are malformed (no NaN)', () => {
    // WS events are unchecked casts; a version-skewed plan could omit rounds.
    const bad = { type: 'graph.plan', analysts: ALL_ANALYSTS } as unknown as DebateEvent;
    const { totals, totalAgents } = derivePhaseTotals([bad]);
    expect(totals).toEqual({ analysts: 4, researchers: 3, trader: 1, risk: 4 });
    expect(totalAgents).toBe(12);
    expect(Number.isFinite(totalAgents)).toBe(true);
  });
});

describe('computeProgress', () => {
  it('marks a Pro rounds=2 run fully done when every turn has streamed', () => {
    const events: DebateEvent[] = [
      plan(ALL_ANALYSTS, 2, 2),
      ...ALL_ANALYSTS.map((a) => msg(`${a}_analyst`, 'analysts')),
      { type: 'phase.transition', from: 'analysts', to: 'researchers' } as DebateEvent,
      msg('bull_researcher', 'researchers', 1),
      msg('bear_researcher', 'researchers', 1),
      msg('bull_researcher', 'researchers', 2),
      msg('bear_researcher', 'researchers', 2),
      msg('research_manager', 'researchers', 2),
      msg('trader', 'trader'),
      msg('risk_aggressive', 'risk', 1),
      msg('risk_conservative', 'risk', 1),
      msg('risk_neutral', 'risk', 1),
      msg('risk_aggressive', 'risk', 2),
      msg('risk_conservative', 'risk', 2),
      msg('risk_neutral', 'risk', 2),
      msg('portfolio_manager', 'risk', 2),
    ];
    const { phases, totalDone, totalAgents } = computeProgress(events);
    const byPhase = Object.fromEntries(phases.map((p) => [p.phase, p]));
    expect(byPhase.analysts).toMatchObject({ done: 4, total: 4, state: 'done' });
    expect(byPhase.researchers).toMatchObject({ done: 5, total: 5, state: 'done' });
    expect(byPhase.trader).toMatchObject({ done: 1, total: 1, state: 'done' });
    expect(byPhase.risk).toMatchObject({ done: 7, total: 7, state: 'done' });
    expect(totalDone).toBe(17);
    expect(totalAgents).toBe(17);
  });

  it('lights up the analysts phase from agent.activity before any message', () => {
    const events: DebateEvent[] = [
      plan(ALL_ANALYSTS, 1, 1),
      { type: 'agent.activity', agent: 'technical_analyst', status: 'using_tools' } as DebateEvent,
    ];
    const { phases } = computeProgress(events);
    const analysts = phases.find((p) => p.phase === 'analysts')!;
    expect(analysts.state).toBe('active');
    expect(analysts.done).toBe(0);
  });

  it('does not count terminal events toward progress', () => {
    const events: DebateEvent[] = [
      plan(['market'], 1, 1),
      msg('technical_analyst', 'analysts'),
      { type: 'run.token_cap', used: 30000, cap: 15000, message: 'stop' } as DebateEvent,
    ];
    const { totalDone } = computeProgress(events);
    expect(totalDone).toBe(1);
  });
});
