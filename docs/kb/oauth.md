---
order: 50
---

# ChatGPT Sign-In (OAuth)

*Use your paid ChatGPT account to power Trading Agents Lab Pro analyses with no API key and no per-token billing.*

> **For educational research and paper trading. This is not investment advice.**

---

## Why sign in?

The standard OpenAI API charges per token. A Full analysis makes many model calls (see [cost-guard.md](cost-guard.md)), so on an API key that adds up to real money per run.

If you already pay for a **ChatGPT** plan, you already have a daily allowance of model usage, but it lives behind a different endpoint family than `api.openai.com`. The sign-in flow routes your analyses through that endpoint instead. Within your plan's rate limits there is no per-token charge.

Sign-in works for both **Full analysis** and **Quick analysis**.

---

## How to connect

1. Open **Settings → LLM Providers**.
2. Find the **OpenAI account (OAuth)** row at the top of the tab. It is separate from the OpenAI API-key row, and you can have both.
3. Click **Connect**. A browser tab opens to OpenAI.
4. Sign in if you are not already, and approve the request.
5. The row updates to show your email and plan, for example *"Connected as you@example.com · plus plan"*, and the pill changes from **Recommended** to **Connected**.

If the browser tab cannot hand the result back to the app within about 20 seconds, the row shows a paste field: *"Browser callback not received. Paste the code from the OpenAI page here."* Paste the code and click **Submit**.

You are connected. On Analyze, **Run with** now shows *OpenAI (OAuth)*, and the model dropdown lists the models your ChatGPT account can use.

To disconnect, click **Disconnect** on the same row and confirm. The access and refresh tokens are erased from the encrypted store.

---

## Plan-tier detection

When sign-in completes, the app reads the plan from the sign-in token (the `chatgpt_plan_type` claim) and shows it next to your email: *"plus plan"*, *"pro plan"*, *"team plan"* and so on.

If the plan comes back as **free**, a banner appears in Settings: free-tier ChatGPT accounts have unreliable Codex routing through the ChatGPT backend, and many models hang or return errors. **Add an OpenAI API key** instead if you are on the free tier.

If the plan cannot be read, the banner does not appear and you can still try an analysis.

---

## What is actually happening

An OpenAI API key calls:

```
https://api.openai.com/v1/chat/completions
```

That is the **per-token billing** endpoint family. It is separate from your ChatGPT plan.

OpenAI's Codex CLI uses a different endpoint, and the sign-in path uses it too:

```
https://chatgpt.com/backend-api/codex/responses
```

Trading Agents Lab Pro's sign-in path uses that Codex backend. Requests carry your sign-in token as a bearer token and your account ID in a `chatgpt-account-id` header, and the response is read as a stream. Both analysis modes use it, and the rest of the engine does not need to know which path is active. The sign-in itself is handled with the MIT-licensed `@earendil-works/pi-ai` package.

Your sign-in tokens stay on your machine, encrypted by your OS keychain. See [security-and-storage.md](security-and-storage.md).

---

## Cost and quota

| Path | Cost | Limit |
|---|---|---|
| OpenAI API key | Per token | API tier rate limits |
| ChatGPT sign-in | No per-token charge | Your ChatGPT plan's rate limits, which vary by plan |

**Important:** analyses on sign-in use your ChatGPT plan's quota. A Full analysis makes many model calls, so several in a row can use a meaningful share of your allowance. If you reach your plan's limit, analyses fail until it resets. The exact limits are not published by OpenAI and can change.

**Verification:** after your first sign-in analysis, check your **OpenAI billing dashboard** to confirm the run did not add to your API usage. Sign-in runs are sent only to the ChatGPT backend, not to api.openai.com. If a run did appear on your API account, open an issue on GitHub.

### Cost Guard and sign-in

Cost Guard records sign-in sessions as $0, so they do not count toward the daily, weekly or monthly USD caps and there is no dollar stop during the run. They **do** count toward the optional sessions-per-day cap, which is the way to protect your ChatGPT allowance. The optional token cap (**Settings → Analysis**, Full analysis only) also applies. See [cost-guard.md](cost-guard.md).

---

## Models available with sign-in

The ChatGPT backend accepts a different, smaller model list than the standard API, and OpenAI changes it on its own schedule. The model dropdown for sign-in is therefore **live**: it shows the models your ChatGPT account can use right now, read from OpenAI when you open Analyze. The first model in that list is the default. A line under the dropdown shows whether the list is live, saved from last time, or the built-in list (if OpenAI could not be reached), with a **Refresh** button.

If a model you picked has been retired, the engine swaps it for your account's current default before the run starts, so the run does not fail on every step.

You cannot pick `gpt-4o`, `gpt-4o-mini` or other API-only models on this path. They are not offered by the ChatGPT backend.

---

## Sign-in versus an API key

Both paths run the same engine, so a sign-in analysis and an API-key analysis go through the same steps with the same tools and the same market data. In a Full analysis that is the research graph described in [how-it-works.md](how-it-works.md), including the analysts' live tool calls (price history, indicators, fundamentals, news).

### What is the same on both paths

- The engine, the agent roster, the debate structure and the tool calls.
- The market data fetched for the same ticker and date.
- The committee assessment fields: stance, conviction, bull and bear thesis strengths, risk level and reasoning (plus the modeled scenario range, time horizon and written thesis in a Full analysis).
- Cost Guard, history, transcripts and webhooks.

### What differs

| | API key | ChatGPT sign-in |
|---|---|---|
| Cost per run | Per token, in real money | No per-token charge within your plan's limits |
| Model choice | The provider's live catalog, and every other provider as well (Anthropic, OpenRouter, Gemini, xAI, MiniMax) | Only the models your ChatGPT account can use (live list) |
| Rate limits | API tier limits | Your plan's limits, which are not published |
| Endpoint | OpenAI's official, versioned API | The ChatGPT backend, which OpenAI can change without notice |

### Choosing, in practice

- **Prefer an API key** if you want the widest choice of models and providers, or limits that are published.
- **Prefer sign-in** if you already pay for ChatGPT and want Full analyses without a per-token bill.
- **You can keep both stored.** When both are present, the sign-in is the one used for OpenAI. To use the API key, disconnect the sign-in, or pick a different provider in **Run with**.

### When your sign-in expires

If OpenAI will not refresh your sign-in, the OAuth row shows an **Expired** pill and a **Sign in again** button, and Analyze shows a notice: *"Your ChatGPT sign-in has expired."* If you also have an OpenAI API key stored, the notice offers **Use API key** for the current session. Otherwise it points you to Settings.

---

## Anthropic and others

Sign-in is **OpenAI only**. Anthropic's Terms of Service do not allow it, so Trading Agents Lab Pro offers only API-key access for Anthropic. OpenRouter, Gemini, xAI and MiniMax are also API-key only.

---

## Troubleshooting

**"Free-tier ChatGPT accounts have unreliable Codex routing" banner.** You are signed in with a free ChatGPT account. Add an OpenAI API key and disconnect the sign-in.

**"Your ChatGPT sign-in has expired."** Click **Sign in again** in Settings, or use **Use API key** on the Analyze notice if you have a key stored.

**A rate-limit error (429).** You have reached your plan's limit. Wait for it to reset, or switch to an API key for the rest of the day.

**An error that a model is not supported with a ChatGPT account.** OpenAI retired that model for sign-in. Click **Refresh** under the model dropdown and pick a model from the live list.

**Connection appears to succeed but analyses fail.** Click **Disconnect**, then **Connect** again to refresh the tokens. If it still fails, use an API key and check your OpenAI account status.

---

## Further reading

- [configuring-llm-providers.md](configuring-llm-providers.md), the main provider page
- [cost-guard.md](cost-guard.md), budget caps and the sessions-per-day cap
- [security-and-storage.md](security-and-storage.md), how sign-in tokens are encrypted at rest
- [troubleshooting.md](troubleshooting.md), the broader troubleshooting guide
- Engine API reference: [docs/api.md](https://github.com/RBJGlobal/TradingAgentsLab-Pro/blob/main/docs/api.md)
