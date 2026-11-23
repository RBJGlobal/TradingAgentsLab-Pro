---
order: 80
---

# Crypto tickers

*Analyze crypto pairs the same way you analyze equities. BTC, ETH, BTC/USD, BTC-USD all work; the engine routes the data strip and News card to the right source automatically.*

> **For educational research and paper trading. This is not investment advice.**

---

## What works today

Type any of the following in the **Ticker** field on the **Analyze** page (the field holds up to 8 characters):

| You type | Engine treats as |
|---|---|
| `BTC` | Bitcoin / USD pair |
| `BTC/USD` | Bitcoin / USD pair (Alpaca format) |
| `BTC-USD` | Bitcoin / USD pair (Yahoo Finance format) |
| `ETH/USDT` | Ethereum / Tether (Alpaca exact pair; yfinance falls back to ETH-USD) |
| `SOL/USD`, `ADA/USD`, `DOGE/USD`, etc. | Resolved per the same rules |

The engine keeps a short list of recognized bare crypto symbols (BTC, ETH, SOL, XRP, ADA, DOGE and others). If you type a recognized symbol like `ETH`, it becomes `ETH/USD`. If you type something the engine does not recognize (`FAKECOIN`), it is treated as an equity symbol, and an input that does not look like either is rejected as "not a valid equity or crypto ticker".

**Full analysis tip.** The normalization above applies to the data strip, the News card and Quick analysis. A Full analysis hands the symbol to the research graph as you typed it, and its analysts look up Yahoo Finance data, which quotes crypto as `BTC-USD`. For a Full analysis on crypto, use the `-USD` form (for example `BTC-USD`).

---

## What you will see on the Data card

The **Data** pill at the top of the page picks up a **"crypto"** badge when the active stream is a crypto ticker. The summary numbers come from the provider you have configured:

- **yfinance** (default, free) uses the `BTC-USD` style symbol. Limited stablecoin pair support; `USDT`/`USDC` pairs collapse to `USD` for yfinance.
- **Alpaca** (optional, requires keys) uses the exact `BTC/USD` pair and hits the dedicated crypto endpoint. Better coverage for stablecoin pairs.

If you have Alpaca configured, the engine routes crypto requests to Alpaca's crypto endpoint. The Data card shows **"alpaca · crypto"** when this happens.

---

## How the analysts handle crypto

**Quick analysis.** The agent prompts are asset-class aware. For crypto tickers, the **fundamental_analyst** is instructed to comment on:

- **Tokenomics**: supply schedule, burn mechanics, issuance
- **On-chain metrics**: active addresses, network volume, hash rate
- **Regulatory**: pending or recent regulatory developments
- **Macro liquidity**: broad market liquidity conditions

It is told to say so explicitly when it does not have detailed data, and to explain what it would look for instead of inventing numbers. The **sentiment_analyst** benefits from asset-class-aware Reddit routing: crypto tickers query `r/CryptoCurrency`, `r/CryptoMarkets` and `r/Bitcoin` instead of `r/wallstreetbets`. See [sentiment.md](sentiment.md).

**Full analysis.** The research graph treats the symbol as an instrument to analyze with its own tools: market data and technical indicators from Yahoo Finance, news from your News source setting, and the StockTwits and Reddit data described in [sentiment.md](sentiment.md) if you enable the Sentiment analyst. For a known crypto symbol the Sentiment analyst searches Reddit by the base symbol (for example `BTC`).

---

## What is not supported

- **Direct USD-pair quotes only.** No DEX prices and no specific exchange (Coinbase versus Kraken versus Binance). You get the consolidated data from the provider.
- **No futures or perpetuals.** Spot pairs only.
- **No on-chain data feeds.** Comments on tokenomics come from what the LLM knows, not from live on-chain feeds.
- **No orders.** Trading Agents Lab Pro is an analysis tool. Crypto analyses cannot place orders, even to Alpaca's crypto endpoints. The app connects only to data endpoints.

---

## News for crypto

The default Yahoo Finance news provider returns crypto news when the ticker is in its database (BTC-USD, ETH-USD, etc.). When Alpaca is the active data provider, the engine asks Alpaca first (its feed covers major crypto such as BTC and ETH) and falls back to Yahoo Finance's crypto news when Alpaca returns nothing. The transition is automatic; the News card shows whichever provider returned headlines.

---

## Troubleshooting

**"not a valid equity or crypto ticker."** The symbol is not on the recognized list and does not look like a ticker. Try the explicit pair form: `ETH/USD` or `ETH-USD`.

**The Data card stays empty for a crypto ticker.** yfinance occasionally has no data for less-traded pairs. Alpaca usually has better coverage for major pairs; see [data-providers.md](data-providers.md) to connect a free account.

**The Sentiment analyst says "no Reddit posts found."** Small crypto tickers do not get much dedicated subreddit discussion. The bullish/bearish ratio from StockTwits is usually still informative.

**The wrong asset class was detected.** The engine decides from a fixed list of known crypto symbols which bare symbols are crypto. A bare symbol that is not on the list is treated as an equity. Type the explicit pair form (`ABC/USD`) to force the crypto path.
