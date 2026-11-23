---
order: 160
---

# Frequently Asked Questions

*Posture, license, what Trading Agents Lab Pro is and is not, and how it relates to the Lite app and the upstream project.*

> **For educational research and paper trading. This is not investment advice.**

---

## Purpose and posture

### What is Trading Agents Lab Pro for?

Trading Agents Lab Pro is an educational research tool and analysis desktop app. It runs a multi-agent AI debate to produce a committee assessment: an analytical stance and thesis strength scores for any ticker you specify.

The app is designed to help you understand how AI agents reason about market data, to practice paper trading, and to build intuition for multi-agent analysis. It is not designed to drive real-money trading decisions.

### Can I use it to trade real money?

No. The app does not place orders of any kind, and it has no brokerage connection. Alpaca, if you add it, is used only to read market data and news, and the app connects only to Alpaca's data service.

The app produces AI-generated analytical assessments, not financial advice. Any real-money decision is entirely your own, and Trading Agents Lab Pro is not a registered investment advisor. If you want assessments sent somewhere else, webhooks can post them to Telegram, Slack, Discord or an HTTPS endpoint you control (see [webhooks.md](webhooks.md)). What happens after that is outside the app.

### Does it guarantee profitable trades?

No. The agent debate produces a committee assessment: an analytical stance on how the bull and bear cases argued, a conviction score, and thesis strength scores. These are model outputs, not probabilities of profit. Past analysis results have no bearing on future returns. This is a research tool.

### Why does the stance use five levels instead of buy, hold or sell?

The app never tells you what to do. Its output is a stance on the evidence: Bullish, Moderately bullish, Neutral, Moderately bearish or Bearish. In a Full analysis the upstream portfolio manager writes a five-step rating, and the app maps it to a stance: Buy to Bullish, Overweight to Moderately bullish, Hold to Neutral, Underweight to Moderately bearish and Sell to Bearish. A price level the portfolio manager names is shown as a **modeled scenario**, not a target. See [how-it-works.md](how-it-works.md).

---

## What Trading Agents Lab Pro is not

- **Not a brokerage.** It does not place orders.
- **Not a registered investment advisor.** Nothing it produces is investment advice.
- **Not a Clawless Computer extension, plugin, add-on, or integration.** It is a standalone product from the same maker. The two share brand-family coherence, not code, and Trading Agents Lab Pro does not connect to Clawless Computer.
- **Not a platform for real-money activity.** Paper trading and study are the intended uses.

---

## Pro and the Lite app

### What is the difference between Pro and the Lite app?

Both are free, open source (AGPL-3.0) desktop apps from the same maker with the same interface family. The Lite app runs a simplified single-pass debate built for watching the pipeline. Trading Agents Lab Pro runs the upstream LangGraph graph: tool-using analysts, multi-round bull and bear and risk debates, and a portfolio-manager assessment with a modeled scenario range and time horizon. Pro also offers **Quick analysis**, a shorter single-model debate similar to the Lite app's. See [how-it-works.md](how-it-works.md).

### Does Pro cost anything?

The app is free. You pay only your own model provider for the calls a run makes, and Cost Guard helps you limit that (see [cost-guard.md](cost-guard.md)).

### Full analysis or Quick analysis, which should I use?

Use **Full analysis** (the default) for the complete research graph. The page shows "Typically 8 to 15 minutes", and it makes many more model calls than Quick analysis. Use **Quick analysis** for a faster, lower-cost pass on one model. Quick analysis also works with local runtimes (Ollama, LM Studio), which Full analysis does not.

---

## License

### What license is Trading Agents Lab Pro under?

Trading Agents Lab additions (the desktop app and engine) are licensed under **AGPL-3.0**. The upstream Python core (`tradingagents/`) is Apache 2.0 and remains Apache 2.0. The source is at [github.com/RBJGlobal/TradingAgentsLab-Pro](https://github.com/RBJGlobal/TradingAgentsLab-Pro).

The `LICENSE` file contains AGPL-3.0. `LICENSE-APACHE` contains the Apache 2.0 text. `NOTICE` records modification and attribution. `CLA.md` describes the Contributor License Agreement.

### What does AGPL-3.0 mean for users?

You can use, modify, and distribute Trading Agents Lab Pro. If you distribute a modified version, you must make the source code of your modifications available under AGPL-3.0. Running it for your own use does not require publishing source.

### What does Apache 2.0 mean for the upstream code?

The `tradingagents/` directory contains code from Tauric Research's TradingAgents, licensed Apache 2.0. It can be used, modified, and distributed freely. The Pro repository preserves that license in `LICENSE-APACHE` and records attribution in `NOTICE`.

---

## Upstream relationship

### Where does Trading Agents Lab Pro come from?

Trading Agents Lab is forked from [Tauric Research's TradingAgents](https://github.com/TauricResearch/TradingAgents), a multi-agent LLM trading research framework. The upstream project implements a LangGraph-based pipeline with analyst, researcher, trader, and risk-manager agents.

Pro runs that graph itself for a Full analysis, with the library's own agent prompts left as published. The app adds a desktop interface, a local engine, key management, data provider options, Cost Guard, and the presentation layer that shows the graph's rating as an analytical stance.

### Are changes being contributed back upstream?

Not at this time. Trading Agents Lab is an independent fork under AGPL-3.0 for its additions.

---

## Clawless Computer relationship

### What is the relationship between Trading Agents Lab and Clawless Computer?

Trading Agents Lab is a **standalone trading companion for [Clawless Computer](https://clawless.ai/)**. It is an independent product with its own codebase, license, and interface. It works fully on its own and has no connection to Clawless Computer in the app. No code is shared between the two products.

---

## LLM providers

### Which LLM providers can I use?

Six cloud provider families are available: **OpenAI**, **Anthropic**, **OpenRouter**, **Google Gemini**, **xAI Grok** and **MiniMax**, plus any **local OpenAI-compatible runtime** (Ollama, LM Studio). Cloud providers use API keys, and OpenAI also supports signing in with a ChatGPT subscription. Full analysis needs an API key or the ChatGPT sign-in. Local runtimes run Quick analysis. See [configuring-llm-providers.md](configuring-llm-providers.md).

### Can I use my paid ChatGPT account instead of an API key?

Yes, for OpenAI only. The sign-in routes runs through the Codex backend at `chatgpt.com/backend-api/codex/responses` (the backend OpenAI's Codex CLI uses), so runs count against your ChatGPT plan limits instead of per-token API charges. See [oauth.md](oauth.md). Free-tier ChatGPT accounts are unreliable here, so paste an API key instead.

### Why is there no Anthropic sign-in?

Anthropic's Terms of Service prohibit OAuth sign-in flows for their API. Trading Agents Lab Pro respects this, so Anthropic is API key only.

### Can I use multiple providers at once?

You can have keys (and the ChatGPT sign-in) for all of them connected at once. Each run uses one provider, chosen with the **Run with** dropdown on the Analyze page. Your model pick is remembered for each provider.

---

## Data and privacy

### Where does market data come from?

Yahoo Finance by default (free, no API key). Optionally Alpaca, which works with a free Alpaca account and also gives fuller news coverage (Benzinga). See [data-providers.md](data-providers.md).

### Does Trading Agents Lab Pro send data to any server?

- Market data is fetched from the data provider you use (Yahoo Finance by default).
- LLM calls go to the provider you chose, using your own key, or, for the OpenAI ChatGPT sign-in, through the Codex backend using your ChatGPT subscription.
- The app has no servers of its own and collects nothing: no telemetry, no analytics, no accounts, no error reports.
- The only other outbound call the app starts is the optional update check to GitHub, which carries no ID for you or your install.

### Are my API keys safe?

Keys are encrypted with your operating system keychain (on macOS, Keychain) before they touch disk, and plaintext is not written to disk. Sign-in tokens are encrypted the same way. See [security-and-storage.md](security-and-storage.md).

### Where is my analysis history stored?

Locally, in a SQLite file named `sessions.db`. The installed app keeps it at `~/Library/Application Support/Trading Agents Lab Pro/sessions.db`, a folder that survives app updates. The History page reads from this file, and each saved run is marked **Full** or **Quick**. To wipe history, quit the app and delete `sessions.db` plus any `sessions.db-wal` and `sessions.db-shm` beside it. The file is not encrypted at rest. Keep it on an encrypted volume such as FileVault if you want at-rest encryption for transcripts.

---

## Further reading

- [Getting started](getting-started.md), install and run
- [How it works](how-it-works.md), the multi-agent pipeline
- [Configuring LLM providers](configuring-llm-providers.md), set up your providers
- [OAuth](oauth.md), ChatGPT subscription routing
- [Cost Guard](cost-guard.md), spending caps
- [Security and storage](security-and-storage.md), how keys are protected
