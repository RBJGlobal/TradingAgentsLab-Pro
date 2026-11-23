---
order: 100
---

# Cost Guard

*Stacked daily / weekly / monthly USD caps and an optional sessions-per-day cap. On by default: $5.00 a day, $15.00 a week and $45.00 a month, with no sessions cap. Override per run.*

> **For educational research and paper trading. This is not investment advice.**

---

## What it is

Cost Guard is a quota layer that sits in front of every paid analysis. Before an analysis starts, the engine estimates its cost and checks it against the caps you have set. If the estimate would push any cap over its limit, the request is blocked and a dialog opens. You can **Cancel**, or **Override and continue**. The override applies to that run only; it does not raise the cap.

In a **Full analysis**, Cost Guard also watches your spending while the analysis runs and stops it if continuing would take you past a cap (see "The mid-run stop" below).

The four limits:

| Dimension | What it limits |
|---|---|
| **Daily** | USD spent across analyses that started today (UTC) |
| **Weekly** | USD spent across analyses that started this week (since Monday 00:00 UTC) |
| **Monthly** | USD spent across analyses that started this calendar month (UTC) |
| **Sessions per day** | The number of analyses started today, regardless of cost |

A cap of `0` means **disabled**. You can enable any subset, for example monthly USD only, or sessions per day only.

### Defaults

A new install starts with a **$5.00 daily**, **$15.00 weekly** and **$45.00 monthly** cap, and no sessions-per-day cap. These are sized so that one Full analysis fits: a Full analysis with all four analysts on Claude Sonnet 4.6 is estimated at about $1.31, and one with only the Market analyst (the setting a new install starts with) at about $0.75.

If you update from an earlier version and your caps were still the old defaults ($1.00 a day, $5.00 a week, $15.00 a month, never changed), they are raised once to the new defaults. Caps you set yourself are kept as they were.

---

## Why it exists

LLM costs scale with the model and the number of calls in ways that are easy to underestimate. A Full analysis makes many model calls, and a larger model or extra debate rounds multiply that. Cost Guard turns "did I just spend $20 on three analyses?" into a deliberate decision instead of a billing surprise.

It also protects against accidental loops and the occasional glitch that starts several analyses. The sessions-per-day cap catches what a USD cap might miss.

---

## Where to go in the UI

**Settings → Cost Guard** contains:

- **Budget caps enabled**, a toggle. When it is off, all paid analyses are allowed regardless of caps.
- **API cost caps (USD)**: **Daily**, **Weekly** and **Monthly** inputs. Set one to 0 to disable that window.
- **Session rate cap**: **Per day**. Set to 0 to disable.
- **Current period spend**: one bar per window, with a **Refresh** link. The sessions bar appears only when a sessions cap is set.
- **Save**. You can change caps at any time, including between analyses.

The **Spend** pill in the status strip at the top of the app shows today's spend against your daily cap. While an analysis runs, the pill adds the running cost of that analysis (for example `$0.42 / $5.00 + $0.0312`), and for a ChatGPT sign-in run it shows *subscription*.

---

## What counts as spend?

The engine prices each session from a built-in rate table (USD per million input and output tokens), updated by hand when providers change prices. When a price is uncertain the table errs high.

| Provider / auth | Cost behavior |
|---|---|
| API key on any per-token provider | Real token usage times the rate table. |
| **OpenAI sign-in** (ChatGPT plan) | **$0.** Billing happens on your ChatGPT plan, outside the app. The ledger records 0, so it reflects only per-token API spend. |
| **Local LLM** (Ollama / LM Studio) | **$0.** |
| **OpenRouter** | Priced at the rate OpenRouter publishes for that model, read when the model list loads. Before the list has loaded (for example right after the app starts), the model is priced from the app's own rate for the same vendor model, or from a deliberately high estimate if there is none. |
| **A model newer than your copy of the app** | Priced from its model family at a deliberately high estimate (for example, $15 and $75 per million input and output tokens for an unknown Claude Opus class model). Never `0.0`: an unpriced model can make Cost Guard stop sooner, never later. A dated model name (such as `claude-haiku-4-5-20251001`) uses the rate of its plain name. |

Sign-in and Local sessions **skip** the three USD caps but **do count** toward the sessions-per-day cap.

A session that stops partway (a cap, an error, or you pressing Stop) is billed for the tokens it already used, and that amount counts toward your daily, weekly and monthly totals even though the run does not appear in History.

---

## The pre-run reservation

Before a paid analysis starts, the app:

1. **Estimates its cost.** How it does so depends on the mode (below).
2. **Reserves** that amount with the engine. The reservation is checked against your caps, and the check is atomic.
3. If it fits, the analysis starts. If it does not, the **Cost Guard dialog** opens.

### Full analysis estimate

A Full analysis runs a multi-agent graph where analysts call data tools as many times as they need, and no single step has a fixed length. No number computed before the run can be a true maximum, so the estimate is a realistic figure: about **1.4 times what a typical run costs**.

It is built step by step: each analyst you selected, every bull and bear turn, the research manager, the trader, every risk-analyst turn, the portfolio manager, and the final thesis-scoring step. The research manager and portfolio manager are priced at your **deep** model and every other step at your **quick** model (both are the model you picked on Analyze). Extra research or risk rounds cost more than the round before, because each new turn reads the whole conversation so far. Models that think before they answer (for example Claude Sonnet 5.5 or gpt-5) get 2.5 times the output budget, since thinking is billed as output.

### Quick analysis estimate

A **Quick analysis** (the shorter single-model debate) has a fixed shape, so Cost Guard reserves a true worst case: twelve agents on your one model, each using its whole output budget, with the transcript growing as each agent reads the ones before it. For a reasoning model, each agent's output budget includes its thinking allowance (1,200 extra tokens), because thinking is billed as output. A Quick analysis has no mid-run stop; the reservation is its protection.

### The dialog

The dialog is titled **Budget cap reached** (or **Session rate cap reached**) and shows:

- Which limit would be exceeded
- Your spend against each enabled cap
- The most the analysis may cost

You then choose:

- **Cancel**: the analysis does not run. Nothing is spent. Pressing Escape also cancels.
- **Override and continue**: the app reserves again with the override flag. The analysis runs, and its cost is added to your totals like any other. **The cap itself does not change.**

The override button is disabled for three seconds after the dialog opens, with a visible countdown, so a double-click cannot skip past it. Cancel is always enabled.

---

## The mid-run stop

Because a Full analysis estimate is not a ceiling, Trading Agents Lab Pro also watches spending while the analysis runs. Before each model call, it checks whether one more call as large as the largest so far could push your spending past a limit, using the same prices that are recorded when the run ends. If it could, the run stops there and the analysis screen says so, for example: *"Stopped: This run reached your Cost Guard daily cap after spending $0.87. Raise the cap in Settings, Cost Guard, or use Override."*

- **A normal run** stops only when continuing could take you past the daily, weekly or monthly cap, whichever has the least room left. The room is rechecked after each step of the analysis, so an analysis started in the meantime is taken into account, and each run's real spend so far counts against the room the others see. A run that costs more than its estimate but stays under your caps finishes normally.
- **An override run** ignores the caps, but stops if it reaches about **3 times its own estimate**. That catches a runaway (a step that never stops calling tools, or a model that keeps thinking). The same runaway stop applies when Cost Guard is turned off or no USD cap is set. The message reads *"Stopped: This run spent $X, about three times its estimate of $Y, so Cost Guard ended it as a likely runaway. Check the models and round counts in Settings, then try again."*
- **ChatGPT sign-in and Local runs** cost $0 per token, so they have no dollar stop. The optional token cap (**Settings → Analysis**, **Max tokens per run**) still applies to a Full analysis.

If the final thesis-scoring step could cross the limit, it is skipped and the analysis ends without the thesis strength bars. A run stopped early produces no committee assessment, but what it spent is added to your totals.

---

## Atomic reservations and expiry

Cost Guard reserves the estimate **atomically**: the database insert of the reservation is the check itself. Two analyses started at the same moment cannot both squeeze under the same cap. The first to insert wins, and the second sees the updated totals and is blocked.

When an analysis ends, its reservation is finalized with the real token usage in place of the estimate. A reservation also has a lifetime, so a crash cannot hold your budget forever:

- A **Full analysis** reservation lives **60 minutes**, because a Full analysis typically takes 8 to 15 minutes and longer with extra rounds.
- A **Quick analysis** reservation lives **15 minutes**.

If the app is killed mid-run, the reservation frees itself when it expires. A run that lasts longer than its reservation still records what it really spent.

---

## When to use which cap

Tune the caps to your comfort:

- **A strict daily cap (for example $2 a day)** suits frequent Quick analyses or Market-only Full analyses.
- **A monthly cap only (for example $30 a month)** suits mixed use and lets you have an expensive day as long as the month stays in budget.
- **A sessions-per-day cap (for example 20)** disciplines sign-in and Local users, whose USD caps never fire. It is also a sensible second cap beside the USD limits.
- **All four enabled** is the strictest setting, useful for unattended or shared use.

---

## What does not count as spend

- **Stub analyses** (no provider configured) are never charged.
- **ChatGPT sign-in analyses** are recorded at $0. Billing is on your ChatGPT plan.
- **Local LLM analyses** are $0.
- **Failed sessions**: if the provider errors before any tokens are spent, the reservation is finalized at 0.

---

## Reading the spend bars

The bars under **Current period spend** show how close you are to each cap:

| Color | Share of the cap used | Meaning |
|---|---|---|
| Green | Under 80% | Plenty of room. |
| Amber | 80% to 99% | You are close to the limit. |
| Red | 100% | You are at or above the cap. The next paid analysis will be blocked. |

For a window with its cap set to 0, the bar shows the raw spend and *cap disabled*.

The **Spend** pill in the status strip uses its own thresholds for the daily cap: green under 50%, amber from 50% to 89%, red from 90%.

---

## Resetting spend

Spend totals are **calendar windows**, not values you can reset. They roll over automatically:

- The daily total resets at **00:00 UTC**.
- The weekly total resets at **00:00 UTC each Monday**.
- The monthly total resets at **00:00 UTC on the first day of each month**.

There is **no manual reset**, by design, so spend history cannot be wiped to get around a cap. If you need to forget all history, you can quit the app and delete `sessions.db` (plus any `sessions.db-wal` and `sessions.db-shm` beside it). The installed app keeps it at `~/Library/Application Support/Trading Agents Lab Pro/sessions.db`; running from source, it is `<repo>/data/sessions.db`. See [security-and-storage.md](security-and-storage.md). This is destructive and not recommended; your History is the same database.

---

## Tracking historical spend

The History page shows each session's estimated cost, and you can sort by date or by **Most expensive**. This is independent of the Cost Guard windows: History does not expire.

---

## Engine API surface

For developers integrating against the engine:

| Endpoint | Purpose |
|---|---|
| `GET /cost-guard/state` | Current spend and config |
| `PUT /cost-guard/config` | Update caps and the enable toggle |
| `POST /cost-guard/check` | Dry run: would this analysis be blocked? |
| `POST /cost-guard/reserve` | Atomic check and reservation; returns a `reservation_id`, or a 402 `CostGuardBlocked` |

Request and response shapes are in [docs/api.md](https://github.com/RBJGlobal/TradingAgentsLab-Pro/blob/main/docs/api.md).
