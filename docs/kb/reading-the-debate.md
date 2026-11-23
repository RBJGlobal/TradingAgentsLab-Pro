---
order: 120
---

# Reading the Debate

*A guided tour of the Analyze page, every element explained, from the input form to the committee assessment.*

> **For educational research and paper trading. This is not investment advice.**

---

## The Analyze page at a glance

Top to bottom, the app shows:

1. **Status strip**, four pills (Engine, Data, LLM, Spend), visible on every page
2. **Page header**, title, a one-line description of the chosen mode, and the Mode, Run with and model pickers
3. **Input card**, ticker, date, Analyze or Stop button, helper text
4. **Debate stream**, session header, progress strip, data summary strip, news card, phase cards, committee assessment
5. **Disclaimer footer**

---

## Page header and pickers

### Mode

**Full analysis** (default) runs the complete research graph. **Quick analysis** runs the shorter single-model debate. The line under the page title changes with the mode. The picker is disabled while a run is streaming, and your choice is remembered. See [how-it-works.md](how-it-works.md).

### Run with and the model picker

**Run with** lists each provider. Providers you have not set up are labeled "(configure in Settings)" and cannot be chosen. The model picker beside it lists the models for that provider and remembers your pick per provider. A **Reset** button appears when you have overridden the recommended provider or model.

For OpenAI with a ChatGPT sign-in and for API-key providers with a live model list, a line under the pickers says whether the list came live from the provider, from a saved copy, or from the built-in list, with a **Refresh** button. If a ChatGPT sign-in has expired, a notice offers to open Settings or switch to your OpenAI API key.

---

## Input card

### Ticker field

Type any ticker symbol. The input converts to uppercase automatically and accepts up to 8 characters. The field is disabled while a run is streaming. For crypto symbols, see [crypto-tickers.md](crypto-tickers.md).

### As-of date field

The date the analysis is anchored to. The date picker is capped at today, because future dates would produce empty data. The field is disabled while a run is streaming.

### Analyze button

Enabled when the engine is running and no run is in flight. Click it, or press `Cmd+Enter`, to start. While a run is streaming, the Analyze button is replaced by the Stop button.

### Stop button

Click it, or press `Cmd+.`, to end the run. Partial results already received stay visible. What a stopped run spent so far still counts toward your Cost Guard totals.

### Helper text

Below the buttons, a one-line status describes the state:

- **Engine starting, please wait.** The engine is starting. This usually clears within a few seconds.
- **Live debate: provider, model.** A provider is set up and the next run will use real models.
- **Stub debate. Paste an LLM key in Settings to switch to live agents.** No provider is set up, so the run is a canned sample.
- **Streaming agent debate from sidecar. Stop to abort.** A run is in flight.
- **Engine could not start after several retries.** The message includes the error and points to the app menu's Restart. See [troubleshooting.md](troubleshooting.md).

### Copy transcript and Open in HTML

After a run completes, two buttons appear. **Copy transcript (Markdown)** copies the full transcript to your clipboard (session header, data summary, headlines and every agent message by phase), and its label briefly shows "Copied". **Open in HTML** writes a standalone reading page and opens it in your default browser.

### Error banner

If the stream closes unexpectedly, a red "Stream error" banner appears under the input card with the message.

---

## Status strip

Four pills sit at the top of the app on every page.

| Pill | What it shows |
|---|---|
| **Engine** | The local engine's health. A pulsing dot with "starting…" while it starts, green when running, red on error. |
| **Data** | The active data source, for example yfinance or alpaca, with "crypto" added for crypto tickers. "pending" until the engine answers. |
| **LLM** | The provider the app will use by default (OpenAI shows "OpenAI · OAuth" for a ChatGPT sign-in). "unconfigured" when none is set up. |
| **Spend** | Today's spend against your daily Cost Guard cap, for example `$0.42 / $5.00`. Green below 50% of the cap, amber from 50%, red from 90%. During a run the in-flight cost is added, and a ChatGPT sign-in run shows "subscription" instead. |

When the engine is in error state, Analyze stays disabled. See [cost-guard.md](cost-guard.md) for the Spend pill and [troubleshooting.md](troubleshooting.md) for engine problems.

---

## Debate stream

The debate stream appears once the first event arrives. It is organized top to bottom in the order below.

### Session header

Shows the ticker and as-of date. While the stream is open, a pulsing "Diligence" badge appears at the right.

### Stop or error banner

If a run ends without an assessment, a banner at the top and a notice at the end explain why:

- **Analysis stopped**, when the token cap or a Cost Guard cap ended the run. The notice says that spend so far still counts, or that you can raise the token cap in Settings.
- **Analysis failed**, when the run hit an error. No assessment is produced.

### Data notice

If Alpaca rejected your saved keys for the run, a notice says so, and the analysis still runs. See [data-providers.md](data-providers.md).

### Progress strip

From the start of a run, a strip shows the four phases (Analysts, Researchers, Trader, Risk) with a count of finished agent turns in each. While running it also shows a short line about what the active phase is doing, a live clock and, for a Full analysis, "Typically 8 to 15 minutes". The footer reads "N of M agents" and, when the run ends, "Diligence complete in" the elapsed time. Totals depend on the mode and settings: in a Full analysis they follow the analysts and rounds you chose, and in Quick analysis they are fixed at 4, 3, 1 and 4.

### Data summary strip

Appears when the price summary arrives. It shows:

- **Last close**, closing price as of the last complete trading day before your as-of date
- **Period change**, percent change over the lookback window, green for positive and red for negative
- **Range**, period low to period high
- **Avg volume**, mean daily volume, shown as M (millions) or K (thousands)
- A line with the number of sessions, the data source and the as-of date

If the data provider could not fetch data (offline, unknown ticker, future date), the strip is absent.

### News card

Shows the recent headlines the app fetched for the ticker and names the source, for example "4 headlines · yfinance". Each headline links to the original article and shows the publisher and a relative time. If no headlines were found, the card is absent. In a Full analysis the News analyst gathers its own headlines using the News source setting, so this card and the analyst's reading can come from different feeds. See [data-providers.md](data-providers.md).

### Phase cards

Agent messages are grouped into phase cards, each with a phase name, a line listing the agents, and one article per message showing the agent name and its text. In a Full analysis, messages from the researcher and risk loops carry a "round N" label. Phases render in order as their first message arrives, and messages append as they stream in.

| Phase | Agents |
|---|---|
| Analysts | technical_analyst, fundamental_analyst, news_analyst, sentiment_analyst |
| Researchers | bull_researcher, bear_researcher, research_manager |
| Trader | trader |
| Risk | risk_aggressive, risk_conservative, risk_neutral, portfolio_manager |

Agent messages are simulated committee speech. They can use trading language such as "buy" or "size down", and that language is the simulated agent speaking inside a research exercise, not an instruction from the app.

### Committee Assessment

Appears when the run completes. The card is titled **Committee Assessment**, and a badge shows "Live", the provider and the model that ran it. It is color-coded by analytical stance:

- **Bullish and Moderately bullish**, green
- **Neutral**, amber
- **Moderately bearish and Bearish**, red

It shows:

- the **stance**
- **Conviction**, as a percentage
- **Bull thesis** and **Bear thesis** strengths, each out of 100, and a **Risk** chip (Low, Moderate or Elevated). If the scoring step could not run, these are hidden.
- **Modeled scenario** and **Horizon**, when the portfolio manager names a price level and time horizon (Full analysis). This is a modeled scenario from the simulated committee, not a target to act on.
- the portfolio manager's **reasoning**
- the line "This assessment is an analytical output of a simulated research committee, not a recommendation. Any investment decision is yours alone."
- token counts and an estimated cost for the run, and a line saying the output is not investment advice and may be inaccurate

In a Full analysis, the stance comes from the upstream five-step rating: Buy shows as Bullish, Overweight as Moderately bullish, Hold as Neutral, Underweight as Moderately bearish and Sell as Bearish. See [how-it-works.md](how-it-works.md).

### Webhooks card

If you have webhooks set up, a card after the assessment lists each one and whether it was fired, filtered or failed. See [webhooks.md](webhooks.md).

---

## Disclaimer footer

The Analyze page ends with a disclaimer: the page is for educational and research purposes only, Trading Agents Lab is not a registered investment advisor, the analyses can be inaccurate or hallucinated, and any decision and its risk are yours. This is not decorative. The app is built for research and paper trading only.

---

## Further reading

- [How it works](how-it-works.md), what each agent is doing and why
- [Keyboard shortcuts](keyboard-shortcuts.md), Cmd+Enter, Cmd+. and navigation shortcuts
- [Troubleshooting](troubleshooting.md), when the stream does not start or stops unexpectedly
