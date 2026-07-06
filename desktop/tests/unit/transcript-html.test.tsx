// The standalone-HTML transcript generator. Locks: document structure,
// markdown rendering through the app's own pipeline, XSS posture (model
// output is escaped, never raw HTML), chat-artifact stripping, and the
// three locked disclaimer tiers being baked in unconditionally.
import { describe, expect, it } from 'vitest';
import { buildTranscriptHtml } from '../../src/lib/transcript-html';
import type { DebateEvent } from '../../src/lib/engine-client';

function sampleEvents(overrides?: { content?: string }): DebateEvent[] {
  return [
    { type: 'session.start', ticker: 'TSLA', trade_date: '2026-07-06' },
    {
      type: 'data.summary',
      last_close: 393.45,
      period_change_pct: -5.92,
      period_low: 368.6,
      period_high: 433.6,
      avg_volume: 48691345,
      sessions: 22,
      source: 'yfinance',
      as_of: '2026-07-02',
    },
    {
      type: 'news.headlines',
      headlines: [
        {
          title: "Tesla's blowout quarter comes with a warning sign",
          url: 'https://example.com/a',
          publisher: 'TheStreet',
          pub_date: '2026-07-06T02:33:00Z',
        },
      ],
    },
    {
      type: 'agent.message',
      phase: 'analysts',
      agent: 'technical_analyst',
      content:
        overrides?.content ??
        '## Trend\n\nPrice is **below** the 50 SMA.\n\n| Indicator | Value |\n|---|---|\n| RSI | 46.77 |',
    },
    {
      type: 'session.complete',
      decision: {
        action: 'SELL',
        confidence: 0.65,
        reasoning: 'Trim into strength; valuation embeds autonomy success.',
        rating: 'Underweight',
        price_target: 337.0,
        time_horizon: '3-6 months',
      },
    },
  ] as unknown as DebateEvent[];
}

describe('buildTranscriptHtml', () => {
  it('produces a standalone document with title, decision, and agent content', () => {
    const { html, suggestedName } = buildTranscriptHtml(sampleEvents());
    expect(suggestedName).toBe('tsla-2026-07-06');
    expect(html).toContain('<!DOCTYPE html>');
    expect(html).toContain('TSLA · 2026-07-06 · Trading Agents Lab Pro');
    expect(html).toContain('class="action sell"');
    expect(html).toContain('rating Underweight');
    expect(html).toContain('price target 337');
    // Markdown rendered, not echoed: bold -> <strong>, table -> <table>.
    expect(html).toContain('<strong>below</strong>');
    expect(html).toContain('<table>');
    expect(html).toContain('46.77');
    // News link present with the external-link hygiene attrs.
    expect(html).toContain('rel="noreferrer noopener"');
  });

  it('bakes in all three locked disclaimer tiers', () => {
    const { html } = buildTranscriptHtml(sampleEvents());
    // Tier 1 (footer line)
    expect(html).toContain('Educational research only · Not a registered investment advisor');
    // Tier 2 (inline under the decision card)
    expect(html).toContain('Verify independently before any action');
    // Tier 3 (page-level full text)
    expect(html).toContain('not a registered investment advisor</strong>');
    expect(html).toContain('large language models can and do hallucinate');
  });

  it('escapes hostile model output instead of injecting it', () => {
    const { html } = buildTranscriptHtml(
      sampleEvents({ content: 'Danger: <script>alert(1)</script> and <img src=x onerror=y>' }),
    );
    expect(html).not.toContain('<script>alert(1)</script>');
    expect(html).not.toContain('<img src=x');
    expect(html).toContain('&lt;script&gt;');
  });

  it('strips chat artifacts from agent reports', () => {
    const { html } = buildTranscriptHtml(
      sampleEvents({
        content:
          'I now have a comprehensive and rich dataset. Let me compile the full analytical report.\n\n---\n\n## Real content\n\nBody text.',
      }),
    );
    expect(html).not.toContain('Let me compile the full analytical report');
    expect(html).toContain('Real content');
  });

  it('handles a minimal event stream without start/decision', () => {
    const events = [
      {
        type: 'agent.message',
        phase: 'analysts',
        agent: 'technical_analyst',
        content: 'Plain finding.',
      },
    ] as unknown as DebateEvent[];
    const { html, suggestedName } = buildTranscriptHtml(events);
    expect(suggestedName).toBe('transcript-session');
    expect(html).toContain('Debate transcript');
    expect(html).toContain('Plain finding.');
  });
});
