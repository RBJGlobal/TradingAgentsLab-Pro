---
order: 70
---

# Data Providers

*Where market data and news come from, what the engine fetches, and how to connect a free Alpaca account for fuller news coverage.*

> **For educational research and paper trading. This is not investment advice.**

---

## Overview

Before any agent speaks, Trading Agents Lab Pro fetches two kinds of data for the ticker and shows them on the Analyze page:

1. **A price summary**: last close, period range, average volume, session count (the data summary strip).
2. **News headlines**: up to 4 recent headlines (the News card). Yahoo Finance is the default; Alpaca is used when connected.

If a fetch fails, the analysis still runs with less context rather than failing.

How the analysts use data depends on the **Mode** you pick on the Analyze page:

- **Quick analysis** hands the price summary and headlines above to the agents as their context block (see [What the analysts see in Quick analysis](#what-the-analysts-see-in-quick-analysis)).
- **Full analysis** runs the upstream TradingAgents analyst team. Each analyst you enable under **Settings → Analysis** gathers its own data with tools: the Market analyst reads prices and technical indicators from Yahoo Finance, the Fundamentals analyst reads company financials, and the News analyst reads news from the source you choose under **Settings → Analysis → News source** (see [News source for the News analyst](#news-source-for-the-news-analyst)). The Sentiment analyst also reads StockTwits and Reddit (see [sentiment.md](sentiment.md)). The summary strip and News card on the Analyze page are still filled in from the provider described below.

---

## Yahoo Finance: the free default

Yahoo Finance is the default data source. It requires no API key and no configuration. The engine is already using it when you first launch the app.

**Settings → Data Providers** shows **Yahoo Finance, Active · default** with no Configure button, because there is nothing to configure.

### What it provides

- **Price summary:** OHLCV bars via the `yfinance` Python package. The engine fetches a 30-session lookback window anchored on the trade date you specify. From that window it computes:
  - Last close (as of the most recent complete trading day before your trade date)
  - Period open, high, low
  - Period change percentage
  - Average daily volume
  - Session count

- **News headlines:** recent headlines from Yahoo Finance's news feed for the ticker, shown on the News card (up to 4). Each headline has a title, publisher, publication date, URL, and summary.

### Limitations

- **No API key means no rate-limit guarantee.** Yahoo Finance is a public feed. It can rate-limit or return empty data on transient network issues. If this happens, the strip or News card is empty and the analysis runs with less data.
- **Weekend and holiday bars are absent.** If you request a trade date that falls on a weekend or holiday, yfinance anchors to the most recent trading day. The `as_of` date in the data summary shows which day was actually used.
- **Future dates return no data.** The date picker is capped at today to prevent this. If the date range contains no bars, the strip stays empty.
- **Unknown tickers return nothing.** When Yahoo Finance has no data for a symbol, the strip stays empty and the analysis still runs.

---

## Alpaca Markets: optional, free data upgrade

Alpaca Markets is an optional second data source. A free Alpaca account (the Basic data plan) is enough; Trading Agents Lab Pro never needs a paid Alpaca subscription.

Alpaca is used **for market data and news only**. The app connects only to Alpaca's data endpoints and has no code path that places orders, so a connected Alpaca account can never trade from Trading Agents Lab Pro.

### Connecting Alpaca

1. Create a free account at alpaca.markets and generate an API key pair in the dashboard. The **Secret** is shown only once, so copy it right away (regenerate the pair if you missed it).
2. In Trading Agents Lab Pro, go to **Settings → Data Providers**.
3. Click **Configure** next to **Alpaca Markets: Key ID** and paste the Key ID.
4. Click **Configure** next to **Alpaca Markets: Secret** and paste the Secret.

Both values are stored in your operating system's encrypted credential store, like your LLM keys. See [security-and-storage.md](security-and-storage.md).

### Checking the connection

When both values are saved, and each time you open the Data Providers tab, Trading Agents Lab Pro checks the keys with one read-only request to Alpaca (it costs nothing and works on the free plan). Both Alpaca rows then show the result:

| Label | Meaning |
|---|---|
| **Connected ✓** | Alpaca accepted the keys. |
| **Key rejected** | Alpaca refused the keys. This usually means the pair was regenerated or deleted on the Alpaca dashboard. Generate a new pair and paste both values again. |
| **Not checked** | Alpaca could not be reached or asked to slow down, so the keys could not be checked. They may still work. Use **Check again** to retry. |
| **Needs Secret** / **Needs Key ID** | Only one of the two values is saved. |

If Alpaca rejects the keys during an analysis, the analysis still runs, and a notice at the top says that it is running without Alpaca data. In a Full analysis the News analyst then reads Yahoo Finance news instead (Yahoo stays as the fallback whenever Alpaca is in use), so it still has news.

### What changes when Alpaca is connected

As soon as both the Key ID and the Secret are saved, every new analysis uses Alpaca automatically. There is no separate switch to flip:

- **Price summary** comes from Alpaca's daily bars instead of yfinance. The **Data** pill and the data summary strip show `alpaca` as the source. In Quick analysis the agents' price context comes from this summary. In a Full analysis the Market analyst still reads its prices and indicators from Yahoo Finance.
- **News headlines** on the News card come from Alpaca's news feed (sourced from Benzinga) instead of Yahoo Finance. Alpaca's feed is often fuller than Yahoo's, which can return no headlines at all for some well-known tickers.
- **The News analyst in a Full analysis** follows the News source setting described below.

Remove either value to go back to Yahoo Finance for both.

---

## News sources

There are two news feeds the app can use:

| Source | Needs a key | Notes |
|---|---|---|
| **Yahoo Finance** | No | The default. Coverage varies by ticker; some tickers return no headlines. |
| **Alpaca (Benzinga)** | Free Alpaca key pair | Used automatically for the News card when Alpaca is connected. Strong coverage for US equities and major crypto. |

For crypto tickers, if Alpaca returns no headlines the engine falls back to Yahoo Finance's crypto news so the News card is not left empty. See [crypto-tickers.md](crypto-tickers.md).

The News card in the debate view always shows which source supplied its headlines.

### News source for the News analyst

In a Full analysis the News analyst looks up news itself during the run, and you choose where it looks. Go to **Settings → Analysis → News source**:

- **Auto (Alpaca when connected, else Yahoo)**: the default. Uses Alpaca (Benzinga) when your Alpaca keys are saved, otherwise Yahoo Finance.
- **Alpaca (Benzinga)**: always tries Alpaca first. If Alpaca is not connected or returns nothing, the analyst falls back to Yahoo Finance.
- **Yahoo Finance**: Yahoo Finance only.

Whenever Alpaca is in use, Yahoo Finance stays as the fallback, so an empty result from one source never leaves the News analyst with no news at all. The News card on the Analyze page does not follow this setting: it uses Alpaca when connected and Yahoo Finance otherwise. Quick analysis does not use this setting either.

---

## Alpha Vantage key (optional)

**Settings → Data Providers** also has an **Alpha Vantage: API key** row, with a **Get a free key** button that opens Alpha Vantage's signup in a separate window inside the app and saves the key it issues. The in-app note says the key is for the News, Social, and Fundamentals analysts, and that without it you should keep the Analysis tab on Market only. The Market analyst needs no key (it runs on Yahoo Finance), and Market is the only analyst selected by default. The key is stored in the encrypted credential store like your other keys and is sent only to Alpha Vantage.

---

## What the analysts see in Quick analysis

In Quick analysis each agent receives a context block containing:

```
Ticker: NVDA
Trade date (anchor): 2026-05-08

Recent price action (compact summary):
- last close: 211.50 (as of 2026-05-07)
- 24-session window: open 177.16, high 216.83, low 173.66, change +19.38%
- avg daily volume: 147,571,146
- source: yfinance

Recent news headlines:
- <headline title> (<publisher>)
- <headline title> (<publisher>)
...
```

This is a deliberate summary, not a raw dataframe. Raw OHLCV tables are noisy and expensive in LLM prompts. In a Full analysis the analysts instead call data tools and write reports from what those tools return.

---

## Crypto data

Both yfinance and Alpaca handle crypto, but their coverage differs:

- **yfinance** uses the `BTC-USD` style symbol. Major pairs (BTC, ETH, SOL, etc.) are well covered. Stablecoin-quoted pairs (`USDT`/`USDC` quotes) collapse to the USD pair, because yfinance does not expose USDT pairs reliably.
- **Alpaca** uses the exact `BTC/USD` pair format and hits a dedicated crypto endpoint. Better coverage for stablecoin-quoted pairs and altcoins.

The engine **auto-routes** crypto tickers to the right endpoint per provider. The **Data** pill on the Analyze page gains a **"crypto"** badge when the active stream is crypto, so you can confirm the engine routed correctly.

See [crypto-tickers.md](crypto-tickers.md) for how tickers are normalized (`BTC`, `BTC/USD`, `BTC-USD` all work in the data strip).

---

## Social sentiment data

Separately from market data, the Sentiment analyst reads public social data (StockTwits and Reddit). No key or account is needed. See [sentiment.md](sentiment.md) for the full details.

---

## Further reading

- [How it works](how-it-works.md), how data fits into the analysis flow
- [Crypto tickers](crypto-tickers.md), symbol normalization and routing
- [Sentiment](sentiment.md), StockTwits and Reddit
- [Troubleshooting](troubleshooting.md), Yahoo Finance returns no data or no news
