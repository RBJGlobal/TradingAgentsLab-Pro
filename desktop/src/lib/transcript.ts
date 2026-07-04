import type {
  DebateEvent,
  QuoteSummary,
  AnalyzeDecision,
  NewsHeadlinesEvent,
} from './engine-client';

const PHASE_LABEL: Record<string, string> = {
  analysts: 'Analysts',
  researchers: 'Researchers',
  trader: 'Trader',
  risk: 'Risk',
};

function findStart(events: DebateEvent[]): { ticker: string; trade_date: string } | null {
  const ev = events.find((e) => e.type === 'session.start');
  return ev && ev.type === 'session.start' ? { ticker: ev.ticker, trade_date: ev.trade_date } : null;
}

function findSummary(events: DebateEvent[]): QuoteSummary | null {
  const ev = events.find((e) => e.type === 'data.summary');
  if (ev && ev.type === 'data.summary') {
    const { type: _t, ...rest } = ev;
    return rest as QuoteSummary;
  }
  return null;
}

function findDecision(events: DebateEvent[]): AnalyzeDecision | null {
  const ev = events.find((e) => e.type === 'session.complete');
  return ev && ev.type === 'session.complete' ? ev.decision : null;
}

function findNews(events: DebateEvent[]): NewsHeadlinesEvent | null {
  const ev = events.find((e) => e.type === 'news.headlines');
  return ev && ev.type === 'news.headlines' ? ev : null;
}

interface PhaseGroup {
  phase: string;
  messages: Array<{ agent: string; content: string }>;
}

function groupByPhase(events: DebateEvent[]): PhaseGroup[] {
  const groups: PhaseGroup[] = [];
  for (const ev of events) {
    if (ev.type !== 'agent.message') continue;
    const last = groups[groups.length - 1];
    if (last && last.phase === ev.phase) {
      last.messages.push({ agent: ev.agent, content: ev.content });
    } else {
      groups.push({
        phase: ev.phase,
        messages: [{ agent: ev.agent, content: ev.content }],
      });
    }
  }
  return groups;
}

export function buildTranscriptMarkdown(events: DebateEvent[]): string {
  const start = findStart(events);
  const summary = findSummary(events);
  const decision = findDecision(events);
  const groups = groupByPhase(events);

  const lines: string[] = [];
  const header = start
    ? `# TradingAgentsLab: ${start.ticker} · ${start.trade_date}`
    : '# TradingAgentsLab: debate transcript';
  lines.push(header, '');
  lines.push(`_Generated ${new Date().toISOString()}_`, '');
  lines.push(
    '> **For educational research and paper trading.** TradingAgentsLab does not provide investment advice.',
    '',
  );

  if (decision) {
    lines.push('## Decision', '');
    lines.push(
      `**${decision.action}** · confidence ${(decision.confidence * 100).toFixed(0)}%`,
      '',
    );
    lines.push(decision.reasoning, '');
  }

  if (summary) {
    lines.push('## Data summary', '');
    lines.push(`- Last close: **${summary.last_close.toFixed(2)}**`);
    const sign = summary.period_change_pct >= 0 ? '+' : '';
    lines.push(`- Period change: **${sign}${summary.period_change_pct.toFixed(2)}%**`);
    lines.push(`- Range: ${summary.period_low.toFixed(2)} to ${summary.period_high.toFixed(2)}`);
    lines.push(`- Avg daily volume: ${Math.round(summary.avg_volume).toLocaleString()}`);
    lines.push(`- Sessions: ${summary.sessions}`);
    lines.push(`- Source: ${summary.source} · as of ${summary.as_of}`);
    lines.push('');
  }

  const news = findNews(events);
  if (news && news.headlines.length > 0) {
    lines.push('## News headlines', '');
    for (const h of news.headlines) {
      const meta = [h.publisher, h.pub_date].filter(Boolean).join(' · ');
      const heading = h.url ? `- [${h.title}](${h.url})` : `- ${h.title}`;
      lines.push(meta ? `${heading} _(${meta})_` : heading);
    }
    lines.push('');
  }

  for (const group of groups) {
    lines.push(`## ${PHASE_LABEL[group.phase] ?? group.phase}`, '');
    for (const msg of group.messages) {
      lines.push(`### ${msg.agent}`, '');
      lines.push(msg.content, '');
    }
  }

  lines.push('---', '');
  lines.push('Transcript exported from TradingAgentsLab.', '');
  return lines.join('\n');
}
