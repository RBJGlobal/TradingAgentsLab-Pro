---
order: 30
---

# Configuring LLM Providers

*How to connect OpenAI, Anthropic, OpenRouter, Google Gemini, xAI Grok, MiniMax or a local runtime; how to pick which provider and model each analysis uses; how keys are stored.*

> **For educational research and paper trading. This is not investment advice.**

---

## What ships today

Trading Agents Lab Pro supports seven LLM provider families:

| Provider | Auth options | Model pre-selected on Analyze | Notes |
|---|---|---|---|
| **OpenAI** | API key **or** ChatGPT sign-in (OAuth) | `gpt-4o-mini` (key) / the first model in your ChatGPT account's live list (sign-in) | Sign-in routes through your ChatGPT plan instead of per-token API billing. See [oauth.md](oauth.md). |
| **Anthropic** | API key only | `claude-sonnet-5-5` | There is no Anthropic sign-in: Anthropic's Terms of Service do not allow it. |
| **OpenRouter** | API key | `openai/gpt-4o-mini` | One key, many models. Useful as a single-key multi-model option. |
| **Google Gemini** | API key | `gemini-3.1-flash-lite` | Gemini 2.5 and 3.x. Gemini 2.0 Flash was retired by Google; a saved 2.0 Flash choice moves to 3.1 Flash-Lite. |
| **xAI Grok** | API key | `grok-4.3` | Grok 4.3 plus the Grok 4.20 family. |
| **MiniMax** | API key | `MiniMax-M2.7-highspeed` | MiniMax M2.x (Global region, 204K context). |
| **Local LLM** | Auto-detect (no key) | Whatever your runtime exposes | Ollama, LM Studio, or any OpenAI-compatible localhost server. Works with Quick analysis only. See [local-llm.md](local-llm.md). |

**Full analysis** (the default mode) runs on an API key or on OpenAI sign-in. A local runtime is available for **Quick analysis** only. Both modes are described in [how-it-works.md](how-it-works.md).

When more than one provider is configured, the priority order is: OpenAI, Anthropic, OpenRouter, Gemini, xAI, MiniMax, Local. Local is last so a paid key is chosen first. You can override that choice at any time with the **Run with** dropdown on Analyze.

---

## Where to go in the UI

Open Settings from the sidebar or press `Cmd+,`. Select the **LLM Providers** tab.

The tab lists an **OpenAI account (OAuth)** row first, then one row for each API-key provider (OpenAI, Anthropic, OpenRouter, Google Gemini, xAI Grok, MiniMax), then the **Local LLM (Ollama / LM Studio)** section.

Each stored key shows a green **Connected ✓** pill, the last 4 characters of the key as a hint, and when it was saved. From there you can **Test** the key (a short request to the provider), **Replace** it or **Delete** it at any time.

You can have both an OpenAI API key and an OpenAI sign-in stored. When both are present, the sign-in is used. See [oauth.md](oauth.md).

---

## Adding a key

1. Go to **Settings → LLM Providers**.
2. Click **Configure** next to the provider you want.
3. Paste your key into the password field. The field is masked.
4. Click **Save**.

The key is encrypted by your OS keychain before it touches disk. You never see it again; only the last 4 characters are displayed afterward.

To replace a key, click **Replace** and paste the new value. To remove a key, click **Delete** and confirm. The encrypted entry is erased from `secrets.json`.

---

## Connecting with ChatGPT sign-in (OpenAI only)

If you have a paid ChatGPT account, you can sign in instead of pasting an API key. In **Settings → LLM Providers**, click **Connect** on the **OpenAI account (OAuth)** row and approve the connection in the browser tab that opens. The row then shows your email and plan, for example *"Connected as you@example.com · plus plan"*.

A banner warns when the plan is **free**, because the ChatGPT backend is unreliable on free accounts. Paste an API key instead in that case.

**Disconnect** erases the stored sign-in tokens. The full flow, what is the same and what differs from an API key, and troubleshooting are in [oauth.md](oauth.md).

---

## Picking which provider runs your analysis

The **Analyze** page header has three pickers:

- **Mode**: **Full analysis** or **Quick analysis**.
- **Run with**: every provider, with the ones you have not set up shown as *(configure in Settings)* and disabled. OpenAI is shown as *OpenAI (OAuth)* when the sign-in is the one in use.
- A **model** dropdown for the selected provider.

Your **Run with** choice is remembered between sessions. Each provider (and OpenAI sign-in, separately from OpenAI with a key) also remembers its own last-chosen model, so switching away and back restores your earlier pick. A **Reset** button appears when you have changed the provider or model from the recommended pre-selection; it clears your manual choices.

Full analysis uses two model roles: a **deep** model for the research manager and the portfolio manager, and a **quick** model for every other step. Both roles use the model you pick in the dropdown. A saved Gemini 2.0 Flash choice moves to Gemini 3.1 Flash-Lite in both. Quick analysis runs every step on the one model you pick.

### The model list is live

The model dropdown shows the models your provider offers **right now**, not a list fixed when the app was built. When an API-key provider is selected (OpenAI, Anthropic, OpenRouter, Google Gemini or xAI Grok), the app asks that provider for its current model list, so new models appear without an app update.

- **Recommended** at the top: a short list picked for the analysis, limited to models the provider still offers. The model marked *(recommended)* is the one used when you have not chosen one.
- **All available** below: every other text model the provider lists. OpenRouter lists hundreds.
- A line under the dropdown says where the list came from: *live from* the provider, a *saved list* from the last time it loaded (with the reason, if the latest attempt failed), or the *built-in list* if the provider has never been reached (with the reason). **Refresh** asks the provider again.
- Your chosen model is **never switched for you**. If the provider's list no longer shows it (for example, it now lists the same model under a dated name), it stays selected and appears at the top as *your saved choice*, or as *saved, not listed by provider* when the provider lists no model by that name at all (runs with it may then fail).
- The request goes from the app's local engine straight to the provider you configured, with your own key, and only for the provider selected in the dropdown. Nothing is sent anywhere else, and the engine does not store the key.
- **MiniMax** keeps its built-in list. **Local** runtimes list whatever you have installed (see [local-llm.md](local-llm.md)). The **OpenAI sign-in** path has its own live list from your ChatGPT account (see [oauth.md](oauth.md)).

### Reasoning models

Some models think before they answer: OpenAI's o-series and gpt-5 and gpt-5-mini, the newer Claude models (Opus 5 and 5.5, Sonnet 5 and 5.5, Haiku 5.5, Fable, Mythos), Gemini 2.5 and 3.x, and OpenRouter models whose catalog entry says they reason. Thinking is billed by the provider as output, so it costs more than a non-reasoning model at the same price.

- In a **Quick analysis**, each agent gets **extra room to think** (1,200 tokens on top of its answer budget) and is asked for a low reasoning effort. If a model still uses all of that room thinking, the turn shows an error instead of a blank answer; pick a non-reasoning model in that case.
- In a **Full analysis**, the research graph does not cap how long a model thinks. Cost Guard budgets reasoning models at 2.5 times the visible output of each step. See [cost-guard.md](cost-guard.md).

**Anthropic reasoning effort** (Settings, Analysis) applies to Full analysis only. It is sent only when both the deep and the quick model accept it: Claude Opus 4.5 and later, Sonnet 4.6 and later, and Fable 5 and later. Haiku models never accept it, and the setting is ignored for other providers.

Cost Guard still applies to a model that is newer than your copy of the app. Models the app has no price for are budgeted at a deliberately high estimate, so a new model can make Cost Guard stop sooner, never later. OpenRouter models are budgeted at the price OpenRouter publishes for them. See [cost-guard.md](cost-guard.md).

### Stub mode

If no provider is configured, **Run with** shows *Stub debate (no LLM configured)* and the analysis is a canned debate that uses real yfinance data. It costs nothing and is useful for checking that the app works. See [how-it-works.md](how-it-works.md).

---

## How keys are stored

Trading Agents Lab Pro uses Electron's `safeStorage` API, which on macOS wraps the Keychain. The file at `<userData>/secrets.json` contains only base64-encoded ciphertext, never plaintext. The exact path is shown in **Settings → About**.

Each entry records:

- `hint`, the last 4 plaintext characters (for identification in the UI, not security)
- `updatedAt`, an ISO-8601 timestamp of the last save
- `cipher`, base64 of the OS-encrypted bytes

The ChatGPT sign-in is stored under a separate `oauth:openai` entry, with the access token, refresh token, expiry, email, account ID and plan all encrypted together.

**The encrypted file is machine- and user-bound.** Copying `secrets.json` to another machine will not work, because the ciphertext cannot be decrypted there. See [security-and-storage.md](security-and-storage.md).

---

## Cost expectations

Your cost depends on the provider, the model and the mode.

- **Stub mode** costs $0.
- **OpenAI sign-in** has no per-token cost, but it uses your ChatGPT plan's quota. See [oauth.md](oauth.md).
- **Local LLM** costs $0 in API fees.
- **Quick analysis** is the shorter single-model debate, so it costs less than a Full analysis on the same model.
- **Full analysis** makes many more model calls. As a reference, Cost Guard estimates about $1.31 for a Full analysis with all four analysts, one round of each debate and Claude Sonnet 4.6 as both models, and about $0.75 with only the Market analyst (the setting a new install starts with). Treat these as planning figures, not a quote.

Cost Guard estimates every paid analysis before it starts and watches spending while a Full analysis runs. The `session.complete` event carries `estimated_cost_usd`, `input_tokens` and `output_tokens`; OpenAI sign-in and local sessions report `estimated_cost_usd: 0`.

To keep costs low:

- Use Quick analysis, or keep Full analysis on the Market analyst with one round of each debate.
- Pick a cheaper model from the dropdown.
- Use the Stop button (`Cmd+.`) to end an analysis early. What was already spent still counts toward your totals.
- Set Cost Guard caps you are comfortable with (**Settings → Cost Guard**).

---

## Further reading

- [how-it-works.md](how-it-works.md), Full and Quick analysis, and stub mode
- [oauth.md](oauth.md), ChatGPT sign-in in depth
- [local-llm.md](local-llm.md), Ollama and LM Studio
- [cost-guard.md](cost-guard.md), budget caps and the mid-run stop
- [security-and-storage.md](security-and-storage.md), detailed key storage model
- [troubleshooting.md](troubleshooting.md), what to do when an analysis fails
- Engine API reference: [docs/api.md](https://github.com/RBJGlobal/TradingAgentsLab-Pro/blob/main/docs/api.md)
