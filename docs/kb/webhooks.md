---
order: 110
---

# Webhooks

*Push every completed analysis's committee assessment to Telegram, Slack, Discord, or your own HTTPS endpoint.*

> **For educational research and paper trading. This is not investment advice.**

---

Webhooks push every completed analysis's committee assessment to your own systems: Telegram, Slack, Discord, or any HTTPS endpoint. Useful for getting notified on a phone while a long analysis runs, logging assessments to a spreadsheet for review later, or handing the analysis output to a script of your own.

**Trading Agents Lab Pro does not place trades.** Webhooks are an analysis handoff. They push the JSON assessment payload to your receivers. The payload carries no trade instruction. If you choose to build automation on top of it, your receiving script owns that decision and acts with your own credentials on a regulated platform. Your app, your auth, your responsibility.

## Where to configure

`Settings → Webhooks → + Add webhook`

Per-webhook you set:

- **Name**: anything human-readable, shown in the post-analysis report
- **Kind**: Telegram, Slack, Discord, or Generic JSON
- **Bot Token** and **Chat ID** (Telegram only)
- **URL**: the webhook endpoint (Slack, Discord, Generic). Treated as a secret and stored encrypted by your operating system.
- **HMAC shared secret (optional)** (Generic only), sent as `X-TAL-Signature: sha256=<hex>`
- **Filter**: fire only on certain stances (**Fire on stances**) and/or at or above a **Minimum conviction** threshold

Filters are optional. Leave the stance checkboxes empty and the conviction slider at 0% to fire on every analysis.

Webhooks fire after both kinds of analysis (Full and Quick), and after each ticker of a Watchlist **Run all** batch. The same list of webhooks applies to all of them.

## Recipes

### Telegram (recommended for phone alerts)

1. On Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`, and follow the prompts. Save the **bot token** it gives you.
2. Message your new bot anything (it has to be messaged first; you cannot add it to a chat cold).
3. Message [@userinfobot](https://t.me/userinfobot). It replies with your numeric **chat ID**.
4. In Trading Agents Lab Pro: `+ Add webhook`, Kind: **Telegram**, paste the token into **Bot Token** and your numeric ID into **Chat ID**.

For group chats: add the bot to the group, send a message in the group, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser to find the negative chat ID (for example `-100123456789`).

### Slack

1. In Slack: `Apps → Incoming Webhooks → Add to Slack → pick channel → save`. Slack gives you a webhook URL.
2. In Trading Agents Lab Pro: Kind: **Slack**, paste the URL. No other fields are needed.

### Discord

1. In a Discord server: `Server Settings → Integrations → Webhooks → New Webhook → pick channel → copy URL`.
2. In Trading Agents Lab Pro: Kind: **Discord**, paste the URL.

Telegram, Slack and Discord receive a short text message: ticker, stance, conviction, the as-of date, the bull and bear thesis strengths and risk level when present, and the first part of the reasoning (about 500 characters), followed by the line "Analytical stance, not a recommendation. Any investment decision is yours alone."

### Generic (your own script / Cloudflare Worker / Lambda)

The payload schema is `tradingagentslab.webhook.v2`. The `decision` block carries the full analytical stance model:

```json
{
  "schema": "tradingagentslab.webhook.v2",
  "event": "session.complete",
  "ticker": "NVDA",
  "trade_date": "2026-05-15",
  "decision": {
    "stance": "bullish",
    "conviction": 0.78,
    "bull_strength": 78,
    "bear_strength": 42,
    "risk_level": "moderate",
    "reasoning": "..."
  },
  "session_id": "01923f...",
  "live": true,
  "provider": "openai",
  "model": "gpt-4o-mini",
  "estimated_cost_usd": 0.0042
}
```

Stance values: `bullish` | `moderately_bullish` | `neutral` | `moderately_bearish` | `bearish`. Conviction is 0 to 1. Bull and bear strengths are 0 to 100 scores. Risk level is `low` | `moderate` | `elevated`. For a Full analysis, `model` is the deep model of the run.

Set an **HMAC shared secret** on the generic webhook to sign the body. Your receiver verifies by recomputing:

```python
import hmac, hashlib
sig = request.headers["X-TAL-Signature"].removeprefix("sha256=")
expected = hmac.new(SECRET.encode(), request.body, hashlib.sha256).hexdigest()
if not hmac.compare_digest(sig, expected):
    return 403
```

### Building your own rule on top (illustrative)

The assessment is analysis, not an instruction: nothing in the payload tells any system to trade, and the app never will. If you choose to build automation on top of it, that mapping from stance to action is a rule **you** define, running on **your** receiver, under **your** credentials and authority. Example of such a rule, a Cloudflare Worker that keeps your own research log:

```ts
export default {
  async fetch(req: Request, env: Env) {
    if (req.method !== 'POST') return new Response('only POST', { status: 405 });
    const body = await req.json<TalAssessment>();

    // Your own rule: keep only bullish assessments with conviction of 75% or more.
    if (!['bullish', 'moderately_bullish'].includes(body.decision.stance)) return new Response('skip');
    if (body.decision.conviction < 0.75) return new Response('skip');

    // Append a row to your own research log (a KV namespace you created).
    const key = `${body.ticker}:${body.trade_date}`;
    await env.RESEARCH_LOG.put(key, JSON.stringify({
      stance: body.decision.stance,
      conviction: body.decision.conviction,
      received_at: new Date().toISOString(),
    }));
    return new Response('ok');
  },
};
```

What you do with your own log is up to you. The app does not see your receiver's data and does not know whether you acted on an assessment.

## Mechanics

- Webhooks fire **once per completed analysis**, after the assessment is produced and the run is saved to History, before the stream closes.
- Each webhook gets a **5-second timeout**. Multiple webhooks fire in parallel, so total wait is roughly the slowest receiver.
- **No retry queue.** If a receiver is down, it shows up as `failed` in the post-analysis report and that is the end of it. Run the analysis again if you need the delivery.
- A run that stops early (a Cost Guard stop, a token cap, or an error) produces no assessment and fires no webhooks.
- Stub analyses (no LLM key configured) fire webhooks too. Handy for testing your receiver without spending provider quota.
- The **Webhooks** card under the debate on the Analyze page shows `fired`, `filtered`, or `failed` per receiver. A filtered receiver shows "filter did not match"; a failed one shows the error or HTTP status. URLs are never displayed in full, so bot tokens stay private.

## Privacy

- The webhook list, including URLs, bot tokens and HMAC secrets, is stored through Electron's `safeStorage`, encrypted at rest by the operating system (the macOS Keychain).
- The settings list shows only the host of each URL.
- URLs and HMAC secrets never appear in the engine's logs.
- URLs never appear in the `webhook.report` event the app receives, so they never end up in History replays.
## What webhooks do not do

- No retry queue. If a webhook fails, it fails for that analysis.
- No batch summary webhook across tickers. A Watchlist **Run all** batch fires per ticker.
- No per-receiver custom payload template. Telegram, Slack and Discord get the short text message; Generic gets the full JSON.
- No scheduled runs. Webhooks fire only after an analysis you start.
