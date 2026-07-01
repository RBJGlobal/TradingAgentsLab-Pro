# Data Providers

*Where market data comes from, what the engine fetches, and how to add Alpaca for power-user data access.*

---

## Overview

The engine fetches two types of data before running a debate:

1. **A price summary**, last close, period range, average volume, session count
2. **News headlines**, recent Yahoo Finance news for the ticker

Both are fetched at the start of every WS session, before any agent speaks. If a fetch fails, the engine degrades gracefully: the debate runs with reduced context rather than failing entirely.

---

## Yahoo Finance: the free default

Yahoo Finance is the default data source. It requires no API key and no configuration. The engine is already using it when you first launch the app.

The Settings page shows **Yahoo Finance, Active · default** in the Data Providers tab with no Configure button, there is nothing to configure.

### What it provides

- **Price summary:** OHLCV bars via the `yfinance` Python package. The engine fetches a 30-session lookback window anchored on the trade date you specify. From that window it computes:
  - Last close (as of the most recent complete trading day before your trade date)
  - Period open, high, low
  - Period change percentage
  - Average daily volume
  - Session count

- **News headlines:** up to 5 recent headlines from Yahoo Finance's news feed for the ticker. Each headline has a title, publisher, publication date, URL, and summary.

### Limitations

- **No API key → no rate-limit guarantee.** Yahoo Finance is a public feed. It can rate-limit or return empty data on transient network issues. If this happens, the engine logs the error and the debate runs in data-offline mode.
- **Weekend and holiday bars are absent.** If you request a trade date that falls on a weekend or holiday, yfinance will anchor to the most recent trading day. The `as_of` field in the data summary shows which day was actually used.
- **Future dates return no data.** The date picker is capped at today to prevent this, but the data provider will raise `DataUnavailable` if the date range contains no bars.
- **Unknown tickers return 404.** The engine returns HTTP 404 from `GET /data/summary` when yfinance has no data for the ticker. The debate still runs, in data-offline mode.

---

## Alpaca Markets: optional power-user data

Alpaca provides IEX/SIP market data feed access under a paid subscription. Adding Alpaca credentials is optional.

**Status today:** The `AlpacaProvider` adapter is planned but not yet implemented. The Data Providers settings tab shows the Alpaca row and accepts an API key, but the engine does not yet use it. When the adapter lands, Alpaca will serve as an alternative (or preferred) data source for live-market feeds with higher reliability than yfinance.

**Same key for data and broker:** The Alpaca API key in the Data Providers tab is the same credential that will also power the Alpaca broker (paper and live trading). You only need one key for both.

To configure the Alpaca key now (for when the adapter ships):

1. Go to **Settings → Data Providers**.
2. Click **Configure** next to Alpaca Markets.
3. Paste your Alpaca API key (`PK…`).
4. Click **Save**.

---

## What the analysts see

Each agent in the debate receives a context block containing:

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

This is a deliberate summary, not a raw dataframe. Raw OHLCV tables are noisy and expensive in LLM prompts. If agents need more detail in later phases, per-agent tools (e.g., RSI/MACD calculation) will be added.

---

## Crypto data

Both yfinance and Alpaca handle crypto, but their coverage differs:

- **yfinance** uses the `BTC-USD` style symbol. Major pairs (BTC, ETH, SOL, etc.) are well covered. Stablecoin-quoted pairs (`USDT`/`USDC` quotes) collapse to the USD pair, yfinance doesn't expose USDT pairs reliably.
- **Alpaca** uses the exact `BTC/USD` pair format and hits a dedicated endpoint at `/v1beta3/crypto/us/bars`. Better coverage for stablecoin-quoted pairs and altcoins.

The engine **auto-routes** crypto tickers to the right endpoint per provider. The **Data** pill on the Analyze page gains a **"crypto"** badge when the active stream is crypto, so you can confirm the engine routed correctly.

See [crypto-tickers.md](crypto-tickers.md) for how tickers are normalized (`BTC`, `BTC/USD`, `BTC-USD` all work).

---

## Social sentiment data

Separately from market data, the engine fetches public social signal (StockTwits + Reddit) for the **sentiment_analyst** agent. This is no-auth, no-key, and runs in parallel with the market data fetch. See [sentiment.md](sentiment.md) for the full details.

---

## Deferred providers

**Massive.com / Polygon-class providers**, institutional-grade tick data and alternative data. Deferred until a feature specifically requires it. Alpaca is sufficient for v1.

---

## Further reading

- [How it works](how-it-works.md), how data fits into the debate flow
- [Crypto tickers](crypto-tickers.md), symbol normalization and routing
- [Sentiment](sentiment.md), StockTwits + Reddit pre-fetch
- [Troubleshooting](troubleshooting.md), yfinance returns no data
- Engine API reference for data endpoints: [docs/api.md](../api.md)
