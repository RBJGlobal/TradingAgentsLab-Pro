---
order: 10
---

# Getting Started

*How to install Trading Agents Lab Pro, add a model key, and run your first analysis.*

> **For educational research and paper trading. This is not investment advice.**

---

## What you need

- **A Mac running macOS 12 or later.** Pro is distributed as a macOS DMG. Other platforms are not tested.
- **An API key from an LLM provider** (or, for OpenAI, a ChatGPT sign-in). Pro bills your own account, so you bring the key. Anthropic is API key only. See [configuring-llm-providers.md](configuring-llm-providers.md).
- **Nothing else.** The Python engine is bundled inside the app. You do not install Python or Node.js.

A Full analysis makes many model calls, so it costs more than a short chat. Cost Guard is on by default and limits spending (see [cost-guard.md](cost-guard.md)).

---

## Step 1: Download and install

1. Download the signed DMG from [tradingagentslab.ai](https://tradingagentslab.ai/download/).
2. Open the DMG and move **Trading Agents Lab Pro** into your Applications folder.
3. Launch it.

The app can check GitHub for newer versions. The request carries no ID for you or your install. See [security-and-storage.md](security-and-storage.md).

---

## Step 2: Accept the first-launch agreement

On first launch a **Before you begin** screen appears. It says the app is an educational research tool and not financial advice, that it is free and open source (AGPL-3.0), and that it collects nothing about you. Choose **I Agree** to continue, or **Decline and Quit** to close the app. You are asked again only if the agreement text changes.

There is no account and no sign-up.

---

## Step 3: Add a model

Open **Settings** (`Cmd+,`) and stay on the **LLM Providers** tab. Add one of:

- an API key for OpenAI, Anthropic, OpenRouter, Google Gemini, xAI Grok or MiniMax (paste it and click **Save**; a **Test** button checks the connection), or
- for OpenAI only, a ChatGPT sign-in (see [oauth.md](oauth.md)).

Full analysis needs an API key or the OpenAI ChatGPT sign-in. A local runtime such as Ollama or LM Studio (see [local-llm.md](local-llm.md)) runs Quick analysis only.

Until you add a provider, the Analyze page shows a **Connect an AI model to run the real analysis** card and runs a built-in sample debate with canned text. Keys are encrypted with your operating system keychain and are sent only to the provider you chose.

---

## Step 4: Run your first analysis

1. Open **Analyze** (`Cmd+1`).
2. Check the **Mode** picker. **Full analysis** is the default. **Quick analysis** is a shorter single-model debate. See [how-it-works.md](how-it-works.md).
3. Check **Run with** (the provider) and the model picker next to it. The page remembers your model pick for each provider.
4. Enter a ticker (the field starts with `NVDA`) and an as-of date (it starts on today).
5. Click **Analyze** (or press `Cmd+Enter`).

While a Full analysis runs, the page shows "Typically 8 to 15 minutes" and a live clock, and the phases fill in as they finish: analysts, researchers, trader, risk. Quick analysis usually finishes in about a minute. Click **Stop** (or press `Cmd+.`) to end a run early.

The result is a **Committee Assessment**: an analytical stance, a conviction score, bull and bear thesis strengths, a risk level and the committee's reasoning, followed by the line "This assessment is an analytical output of a simulated research committee, not a recommendation. Any investment decision is yours alone." See [reading-the-debate.md](reading-the-debate.md).

The status strip at the top of the app has four pills: **Engine**, **Data**, **LLM** and **Spend**. Wait for Engine to show a green dot before you run. It usually takes a few seconds after launch.

---

## Next steps

- [Configuring LLM providers](configuring-llm-providers.md), add keys and pick models
- [Reading the debate](reading-the-debate.md), what each part of the Analyze page means
- [How it works](how-it-works.md), Full analysis and Quick analysis
- [Cost Guard](cost-guard.md), spending caps and the live spend pill
- [Keyboard shortcuts](keyboard-shortcuts.md), speed up your workflow

---

## For developers

Most people never need this. To run Pro from source, clone [github.com/RBJGlobal/TradingAgentsLab-Pro](https://github.com/RBJGlobal/TradingAgentsLab-Pro) and follow its README: create a Python virtual environment at `engine/.venv`, install `engine/requirements.txt`, then run `npm install` and `npm run dev` in `desktop/`. The Electron main process starts the engine for you. Our additions are AGPL-3.0, and the bundled upstream `tradingagents/` package stays Apache 2.0.
