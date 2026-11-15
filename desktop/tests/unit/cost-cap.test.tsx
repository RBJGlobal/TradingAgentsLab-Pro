// @vitest-environment happy-dom
//
// Pro Cost Guard renderer pieces: the reserve request carries the Pro run
// shape (so the engine uses its Pro estimate and stores the mid-run stop),
// aborted runs are treated as spend-settling, and a run.cost_cap event shows
// a "stopped" notice with the engine's message.
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import DebateStream, { findTerminal } from '../../src/components/DebateStream';
import {
  SPEND_SETTLED_EVENT_TYPES,
  buildProReserveRequest,
} from '../../src/lib/cost-guard';
import type { DebateEvent } from '../../src/lib/engine-client';

afterEach(() => cleanup());

const CAP_MESSAGE =
  'Stopped: This run reached your Cost Guard daily cap after spending $0.87. ' +
  'Raise the cap in Settings, Cost Guard, or use Override.';

const COST_CAP: DebateEvent = {
  type: 'run.cost_cap',
  used_usd: 0.87,
  limit_usd: 0.9,
  reason: 'cap',
  dimension: 'daily',
  message: CAP_MESSAGE,
};

describe('buildProReserveRequest', () => {
  it('sends the provider and the cost-relevant Pro fields', () => {
    const req = buildProReserveRequest(
      { provider: 'anthropic', auth: { type: 'api_key' }, model: 'claude-sonnet-4-6' },
      {
        deep_think_llm: 'claude-opus-4-8',
        quick_think_llm: 'claude-sonnet-4-6',
        selected_analysts: ['market', 'news'],
        max_debate_rounds: 2,
        max_risk_discuss_rounds: 1,
      },
      400,
    );
    expect(req).toEqual({
      model: 'claude-opus-4-8',
      auth_kind: 'api_key',
      max_tokens: 400,
      provider: 'anthropic',
      pro: {
        deep_think_llm: 'claude-opus-4-8',
        quick_think_llm: 'claude-sonnet-4-6',
        selected_analysts: ['market', 'news'],
        max_debate_rounds: 2,
        max_risk_discuss_rounds: 1,
      },
    });
  });

  it('falls back to the provider model when no deep model is set', () => {
    const req = buildProReserveRequest(
      { provider: 'openai', auth: { type: 'oauth' }, model: 'gpt-6-luna' },
      {},
      400,
    );
    expect(req.model).toBe('gpt-6-luna');
    expect(req.auth_kind).toBe('oauth');
  });
});

describe('spend refresh on aborted runs', () => {
  it('treats every Pro terminal event as spend-settling', () => {
    for (const t of ['session.complete', 'run.cost_cap', 'run.token_cap', 'run.error']) {
      expect(SPEND_SETTLED_EVENT_TYPES.has(t)).toBe(true);
    }
    expect(SPEND_SETTLED_EVENT_TYPES.has('agent.message')).toBe(false);
  });
});

describe('run.cost_cap notice', () => {
  it('maps to a cost_cap terminal state with the engine message', () => {
    expect(findTerminal([COST_CAP])).toEqual({ kind: 'cost_cap', message: CAP_MESSAGE });
  });

  it('renders a stopped notice, not a failure', () => {
    render(
      <DebateStream
        events={[
          { type: 'session.start', ticker: 'NVDA', trade_date: '2026-11-13' } as DebateEvent,
          COST_CAP,
        ]}
        isStreaming={false}
      />,
    );
    const notice = screen.getByTestId('terminal-notice');
    expect(notice.getAttribute('data-terminal')).toBe('cost_cap');
    expect(notice.textContent).toContain('Analysis stopped');
    expect(notice.textContent).toContain(CAP_MESSAGE);
    // No em or en dashes in user-facing copy.
    expect(notice.textContent).not.toMatch(/[–—]/);
  });

  it('also shows the stop as a banner at the top of the stream', () => {
    const { container } = render(
      <DebateStream
        events={[
          { type: 'session.start', ticker: 'NVDA', trade_date: '2026-11-13' } as DebateEvent,
          COST_CAP,
        ]}
        isStreaming={false}
      />,
    );
    const banner = screen.getByTestId('terminal-banner');
    expect(banner.getAttribute('data-terminal')).toBe('cost_cap');
    expect(banner.getAttribute('role')).toBe('alert');
    expect(banner.textContent).toContain(CAP_MESSAGE);
    // The banner comes before the bottom notice in document order.
    const nodes = Array.from(container.querySelectorAll('[data-testid]'));
    const ids = nodes.map((n) => n.getAttribute('data-testid'));
    expect(ids.indexOf('terminal-banner')).toBeLessThan(ids.indexOf('terminal-notice'));
  });

  it('shows no banner for a run that completed', () => {
    render(
      <DebateStream
        events={[{ type: 'session.start', ticker: 'NVDA', trade_date: '2026-11-13' } as DebateEvent]}
        isStreaming={false}
      />,
    );
    expect(screen.queryByTestId('terminal-banner')).toBeNull();
  });
});
