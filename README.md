# Trading Agents Lab Pro

> **The full-depth companion to [Trading Agents Lab](https://github.com/RBJGlobal/TradingAgentsLab): the same desktop interface, wired to the complete upstream multi-agent research pipeline. Free, open source, bring-your-own-key, zero data collection.**

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Upstream: Apache 2.0](https://img.shields.io/badge/Upstream-Apache%202.0-green.svg)](LICENSE-APACHE)
[![No Tracking](https://img.shields.io/badge/Tracking-Zero-brightgreen.svg)](#privacy-zero-data-collection)

> **For educational research only.** Trading Agents Lab Pro is **not** a registered investment advisor and does not provide investment, financial, legal, or tax advice. LLM-generated analyses can be inaccurate or hallucinated. Nothing this software produces is a recommendation to buy, sell, or hold any security, cryptocurrency, or other asset. See the [full disclaimer](#disclaimer) below.

Trading Agents Lab Pro runs the real research pipeline from the upstream [TradingAgents](https://github.com/TauricResearch/TradingAgents) project inside a native desktop app: four tool-using analysts (market, fundamentals, news, social sentiment), a bull and bear researcher debate over multiple rounds, a trader synthesis, a three-seat risk committee, and a portfolio manager who chairs the final read. The output is a **Committee Assessment**: an analytical stance (Bullish, Moderately bullish, Neutral, Moderately bearish, Bearish), a conviction level, bull and bear thesis strengths, and a risk level. The app never issues a trade instruction. You read how each side argued, and any investment decision is yours alone.

## How Pro relates to the free app

Both apps are free and open source, from the same maker, with the same interface family.

| | Trading Agents Lab (free) | Trading Agents Lab Pro |
|---|---|---|
| Engine | Simplified single-pass debate, built for watching the pipeline | The full upstream LangGraph graph: live tool calls, multi-round debates, agent memory |
| Agents | 8 seats, one turn each | 12 roles, iterative debate rounds |
| Data | Price summary + headlines fed once | Analysts fetch price history, indicators, fundamentals, and news themselves at tool-call time |
| Typical run | About a minute | 8 to 15 minutes of genuine research depth |
| License | AGPL-3.0 | AGPL-3.0 |

If you want a quick read, use the free app. If you want to watch a research desk actually work, use Pro.

## Mission

> *Trading Agents Lab provides a high-quality, professional-grade tool purely for educational purposes. We do not force user adoption and we do not provide trading tools, we provide a free resource for analysis and learning.*

## Why open source

The strongest answer to "what is this app really doing?" is "read it." Trading Agents Lab Pro is a teaching artifact: the codebase demonstrates how a production multi-agent LLM system is orchestrated, metered, and presented, and it serves as a practical case study for [Clawdemy.org](https://clawdemy.org), an AI education platform. Read the source to learn; fork it to build something new.

## Bring your own key

Pro makes dozens of model calls per run, billed to credentials you own:

- **Anthropic, OpenAI, Google Gemini, OpenRouter and more** via API key.
- **ChatGPT subscription (OAuth)** support for running the full pipeline at no per-token cost is under active development on the `oauth-real-graph` branch.
- Optional **Alpha Vantage** key unlocks the fundamentals, news, and social analysts; without it the market analyst runs on free data.

A built-in Cost Guard reserves against your configured daily, weekly, and monthly caps before every run and meters actual token usage while it streams.

## Privacy: zero data collection

No analytics, no telemetry, no error reporting, no accounts, no install pings. The renderer talks only to a local engine on `127.0.0.1`. Outbound calls go exclusively to the providers you configure. Transcripts and history are stored locally on your machine.

## Developing

```sh
# engine (Python 3.12)
cd engine && python -m venv .venv && .venv/bin/pip install -e .. -r requirements.txt

# desktop (Electron + Vite + React)
cd desktop && npm install && npm run dev
```

`npm run dev` starts Vite and Electron; Electron spawns the Python engine from the repo root. Tests: `engine/.venv/bin/python -m pytest engine/tests/` and `cd desktop && npx vitest run`.

## License

- Our application code (desktop app and engine) is licensed **AGPL-3.0** (see [LICENSE](LICENSE)).
- The bundled upstream `tradingagents/` research core from [Tauric Research](https://github.com/TauricResearch/TradingAgents) remains **Apache-2.0** (see [LICENSE-APACHE](LICENSE-APACHE) and [NOTICE](NOTICE)) and is included unmodified.

## Disclaimer

**For educational and research purposes only.** Trading Agents Lab Pro is **not a registered investment advisor** and does not provide investment, financial, legal, or tax advice. The multi-agent LLM analyses this software produces may be inaccurate, incomplete, or outdated: large language models can and do hallucinate. Nothing produced by this software is a recommendation to buy, sell, or hold any security, cryptocurrency, or other asset. Consult a qualified financial professional before making any investment decision. You assume all risk for any action you take based on this software's output. The maintainers and contributors accept no liability for losses arising from use of this software.
