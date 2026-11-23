---
order: 90
---

# Social sentiment (StockTwits + Reddit)

*The Sentiment analyst grounds its analysis in real social data: bullish/bearish ratios from StockTwits and recent discussion from finance subreddits. No API key required.*

> **For educational research and paper trading. This is not investment advice.**

---

## What it does

Before the Sentiment analyst writes anything, the app fetches two social data sources for the ticker:

1. **StockTwits**: recent messages tagged with the ticker (for example `$NVDA`, `$BTC.X`). Each message includes a user-labeled **Bullish** / **Bearish** / no-label tag.
2. **Reddit**: recent posts from finance subreddits that mention the ticker.

Both are public, no-auth, no-API-key endpoints. The fetched text is placed in the Sentiment analyst's prompt as structured blocks, so the analyst can comment on real data (for example, "StockTwits is 60% bullish but r/wallstreetbets is uniformly skeptical, divergence suggests retail enthusiasm without institutional follow-through") instead of inventing posts.

The two analysis modes use this data slightly differently:

| | Quick analysis | Full analysis |
|---|---|---|
| Who fetches it | The engine, once, before the debate starts, in parallel with the price summary and headlines | The Sentiment analyst node itself, when it runs |
| Which analyst gets it | Only the `sentiment_analyst` agent (the other agents read its conclusion in the transcript) | The Sentiment analyst, alongside a news block |
| When it runs | Always (it is one of the twelve agents) | Only if **Social sentiment** is ticked under **Settings → Analysis → Analysts**. The default selection is Market only. |
| Subreddits | Asset-class aware (see below) | `r/wallstreetbets`, `r/stocks`, `r/investing` for every ticker |
| Reddit post size | Up to 5 posts per subreddit, past 7 days, with upvote and comment counts | Up to 5 posts per subreddit, past 7 days, read from Reddit's public feed (scores and comment counts may be absent) |
| StockTwits | Up to 30 most-recent messages | Up to 30 most-recent messages |

In Full analysis the Sentiment analyst returns a structured report with a sentiment band, a score and a confidence, so the header of its report has the same shape from run to run.

---

## Why it matters

LLMs under prompt pressure will invent Reddit posts and StockTwits messages, which is misleading and cannot be checked. The fix is to hand the agent the actual messages. The prompt instructs the agent to **quote ratios**, **name specific subreddits**, and **flag divergence** between the social tone and the price action. If the data is missing or sparse (small-cap tickers, weekends, new symbols), the agent is told to say so explicitly and fall back to the other data it has.

---

## How the data is sourced

| Source | URL | Auth | Volume |
|---|---|---|---|
| StockTwits | `api.stocktwits.com/api/2/streams/symbol/{ticker}.json` | None | Up to 30 most-recent messages |
| Reddit | `reddit.com/r/{sub}` search | None | Up to 5 posts per subreddit, past 7 days |

In Quick analysis, Reddit is queried across **asset-class-aware subreddit sets**:

- **Equities:** `r/wallstreetbets`, `r/stocks`, `r/investing`
- **Crypto:** `r/CryptoCurrency`, `r/CryptoMarkets`, `r/Bitcoin`

The routing happens automatically based on how the ticker is normalized (see [crypto-tickers.md](crypto-tickers.md)). A small delay between requests keeps the app under Reddit's public per-IP rate limit.

In Full analysis, the Reddit search uses the three equity subreddits for every ticker, and a crypto symbol is searched by its base (for example `BTC`).

Both fetchers **degrade gracefully**: a timeout, an HTTP error or a malformed response produces a placeholder note, never a crash. The agent always sees either real data or a clear `<unavailable>` marker. In Full analysis, a failed Reddit fetch is labeled as a failed fetch, not as an absence of posts.

---

## What the prompt sees

In Quick analysis the Sentiment analyst's user message includes structured blocks like:

```
StockTwits messages (most recent):
Bullish: 12 (40%) · Bearish: 6 (20%) · Unlabeled: 12 · Total: 30 most-recent messages

[2026-05-14T10:00:00Z · @user1 · Bullish] long calls into earnings
[2026-05-14T10:05:00Z · @user2 · Bearish] overvalued imo
...

Reddit posts (past 7 days):
r/wallstreetbets, 4 recent posts mentioning NVDA:
  [2026-05-13 ·   42↑ ·  15c] DD on NVDA earnings setup
    body excerpt: I think this prints...
  ...
```

Long message bodies are truncated to about 280 characters (StockTwits) and about 240 characters (Reddit) to keep the prompt small.

---

## Why Quick analysis sends the data only to the Sentiment analyst

In Quick analysis the full StockTwits and Reddit blocks go only into the sentiment analyst's prompt. The other agents (analysts, researchers, trader, risk seats, portfolio manager) read the sentiment analyst's **conclusion** through the transcript instead. This is by design:

- **Token budget.** Putting the full social blocks into every prompt would roughly double total session input tokens.
- **Role separation.** A research desk does not have every analyst reading raw StockTwits; they read the sentiment analyst's summary note. Each role works best with data tailored to its job.

In Full analysis the same idea applies through the graph: the other analysts, the bull and bear researchers, and the rest of the committee read the Sentiment analyst's report, not the raw posts.

---

## Privacy

The only data leaving your machine for sentiment purposes is **the ticker symbol**, as for any other data fetch. StockTwits and Reddit see:

- An HTTP request with the ticker in the URL
- A User-Agent string that names the project

No user identifier, no auth token, no account ID. The fetchers do not keep anything from the responses beyond the formatted text that goes into the prompt.

---

## What is not covered

- **Twitter / X**: no public no-auth API exists. It is not fetched.
- **Discord**: no public API for ticker-specific discussion at scale.
- **YouTube**: no targeted ticker-discussion endpoint that fits this pattern.
- **TradingView ideas**: no public API.

The current sources are a two-source baseline, not exhaustive social coverage. The Sentiment analyst's role is to make the signal-versus-noise judgment in its commentary.

---

## Troubleshooting

**The Sentiment analyst says "no StockTwits messages found."** The ticker does not have a StockTwits stream, or has very few messages. Less-traded equities and obscure crypto pairs often hit this. The agent falls back to the other data it has and says so.

**"stocktwits unavailable: HTTPError" or "URLError."** The StockTwits API is rate-limiting or unreachable. The analyst runs without that block; the Reddit block (when present) still gives some signal.

**Reddit posts feel stale.** The search covers the past 7 days. For a fast-moving event (earnings day, an outage), the most recent posts may already be hours old. For more current signal, check the news headlines instead.

**Reddit says "fetch failed, not an absence of posts" (Full analysis).** Reddit refused or rate-limited the request. Run the analysis again a few minutes later.

**The subreddits are fixed.** The subreddit lists cannot be changed from the app.

---

## Credits

The StockTwits and Reddit integration comes from the upstream [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) project, which redesigned its sentiment analyst after reports of fabricated content from the earlier social-media analyst. Trading Agents Lab Pro's Full analysis runs the upstream analyst; Quick analysis uses a port of the same data sources adapted to the engine's async design, with asset-class-aware subreddit routing.
