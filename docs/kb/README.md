# Trading Agents Lab Pro, Knowledge Base

*Entry point for users of Trading Agents Lab Pro: what it is, how to set it up, and how to get the most out of it.*

Trading Agents Lab Pro is a free, open-source desktop application for educational market research and paper trading. It runs the full upstream TradingAgents research graph: tool-using analysts (market, fundamentals, news, social sentiment), bull and bear researchers, a trader, a risk committee and a portfolio manager. They work on a ticker and date you specify, then produce a committee assessment: an analytical stance, a conviction score, thesis strength scores and reasoning. A shorter Quick analysis mode runs a single-model debate. The analysis is for research and paper-trading purposes only. It is not investment advice.

Trading Agents Lab Pro is a standalone trading companion for [Clawless Computer](https://clawless.ai/): an independent product with its own codebase and license, with no connection to Clawless Computer in the app. It is the full-depth companion to the Lite app, Trading Agents Lab. Both are free and open source under AGPL-3.0, and neither collects any data.

> **For educational research and paper trading. This is not investment advice.**

---

## Files in this knowledge base

| File | What it covers |
|---|---|
| [getting-started.md](getting-started.md) | Download the DMG, accept the first-launch agreement, add a model, run your first analysis |
| [how-it-works.md](how-it-works.md) | Full analysis and Quick analysis, the multi-agent pipeline, how the assessment is produced (with diagrams) |
| [configuring-llm-providers.md](configuring-llm-providers.md) | Add API keys for OpenAI, Anthropic, OpenRouter, Google Gemini, xAI Grok and MiniMax; model picker; how keys are stored |
| [local-llm.md](local-llm.md) | Auto-detected Ollama / LM Studio / llama.cpp runtimes, free and private Quick analysis |
| [oauth.md](oauth.md) | ChatGPT subscription routing via OAuth: what it is, how it works, plan-tier detection |
| [data-providers.md](data-providers.md) | yfinance (free default) and Alpaca (optional, free); news sources and the News source setting |
| [crypto-tickers.md](crypto-tickers.md) | BTC, ETH, BTC/USD and similar: how crypto tickers are normalized and routed |
| [sentiment.md](sentiment.md) | StockTwits and Reddit data for the sentiment analyst |
| [cost-guard.md](cost-guard.md) | Daily, weekly and monthly USD caps and a rate cap; reservations, the live spend pill and the per-run override flow |
| [webhooks.md](webhooks.md) | Push committee assessments to Telegram, Slack, Discord or your own HTTPS endpoint |
| [reading-the-debate.md](reading-the-debate.md) | Walk through every element of the Analyze page as a run progresses |
| [keyboard-shortcuts.md](keyboard-shortcuts.md) | Menu accelerators and page-level shortcuts |
| [security-and-storage.md](security-and-storage.md) | Where keys, sign-in tokens and session history live on disk; encryption model |
| [troubleshooting.md](troubleshooting.md) | Common problems and remedies |
| [faq.md](faq.md) | Posture, license, what Trading Agents Lab Pro is not, the Lite app and the upstream relationship |

---

## Recommended reading order for new users

1. [getting-started.md](getting-started.md), install the app and run a first analysis
2. [configuring-llm-providers.md](configuring-llm-providers.md), connect a provider so runs use real models
3. [reading-the-debate.md](reading-the-debate.md), understand what you are looking at
4. [how-it-works.md](how-it-works.md), go deeper on Full analysis, Quick analysis and how the assessment is produced
5. [cost-guard.md](cost-guard.md), set spending caps before running Full analyses
6. [faq.md](faq.md), licensing, posture and the upstream relationship

If you have a paid ChatGPT account and want to use it instead of an OpenAI API key, jump to [oauth.md](oauth.md) after the getting-started page.

---

## Technical reference

- [Engine API contract](https://github.com/RBJGlobal/TradingAgentsLab-Pro/blob/main/docs/api.md)
- [Full architecture](https://github.com/RBJGlobal/TradingAgentsLab-Pro/blob/main/docs/architecture.md)
