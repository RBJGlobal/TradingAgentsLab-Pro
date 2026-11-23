---
order: 40
---

# Local LLM (Ollama / LM Studio)

*Run a Quick analysis entirely on your own machine with Ollama or LM Studio: no API key, no per-token bill, and the model runs locally.*

> **For educational research and paper trading. This is not investment advice.**

---

## What it is

Trading Agents Lab Pro can route a **Quick analysis** through a local LLM runtime: Ollama, LM Studio, llama.cpp's server, or any OpenAI-compatible server you run on your machine. There is no API fee, and the model runs on your computer. The trade-off is quality: results depend entirely on the model you have installed, and a small model on a laptop is meaningfully weaker than a large hosted model.

**Local runtimes work with Quick analysis only.** A **Full analysis** (the research graph with its tool-calling analysts) needs an API key or ChatGPT sign-in. If you start a Full analysis with Local selected, the run stops with this message: *"Pro engine requires an API key or OpenAI OAuth; local auth is not supported for the full-graph analysis."* Switch **Mode** to **Quick analysis** on the Analyze page to use your local model.

Local is fully optional. If you have a paid key configured, the app prefers it. Local appears in the **Run with** dropdown, so you can choose it whenever you want a zero-cost, local run.

---

## Auto-detection

Open **Settings → LLM Providers** and scroll to the **Local LLM (Ollama / LM Studio)** section. When the section opens, the engine probes three well-known localhost endpoints in parallel:

| Runtime | Probe URL |
|---|---|
| Ollama | `http://localhost:11434/v1/models` |
| LM Studio | `http://localhost:1234/v1/models` |
| llama.cpp server | `http://localhost:8080/v1/models` |

Each probe has a 1.5-second timeout, so the section appears quickly even if nothing is running. A runtime that responds with a model list gets a row showing its name and URL, and a **Model** dropdown listing every installed model. Pick a model from the dropdown. The app stores your (URL, model) choice, shows a **Connected** badge, and the section shows *Active: your-model at the URL*.

If nothing is detected, the section shows links to install [Ollama](https://ollama.com) or [LM Studio](https://lmstudio.ai). Install one, click **Refresh**, and your runtime should appear.

> **What auto-detection does not do:** it does not scan your disk for model files (`.gguf`, `.safetensors`, and so on). Model files without a runtime cannot be used. You need Ollama or LM Studio to provide the HTTP serving layer.

---

## Setting up Ollama

1. Install Ollama from [ollama.com](https://ollama.com).
2. Pull a model, for example `ollama pull llama3.2` or `ollama pull qwen2.5:7b`. A larger model usually reasons better and runs slower.
3. Ollama starts as a background service and listens on `http://localhost:11434`. The app uses the OpenAI-compatible base URL `http://localhost:11434/v1`. To check that it is up, run `curl http://localhost:11434/v1/models`.
4. In the app, open **Settings → LLM Providers**, click **Refresh**, and pick your model in the Ollama row.

> **Ollama and LM Studio differ:** Ollama serves every model you have pulled, so there is no "start server" step. The model id you select must match the `ollama list` tag exactly, and Ollama adds `:latest` when you pull without a tag (so `ollama pull llama3.2` is served as `llama3.2:latest`). Picking from the dropdown handles this for you. It only matters if you type a model id by hand in the manual entry form.

---

## Setting up LM Studio

1. Install LM Studio from [lmstudio.ai](https://lmstudio.ai).
2. Download a model through LM Studio's built-in catalog.
3. Open LM Studio's **Local Server** tab and click **Start Server**. By default it listens on `http://localhost:1234`.
4. In the app, click **Refresh** in the Local LLM section. LM Studio appears with the model that is currently loaded.

> **Heads-up:** LM Studio only exposes the model that is loaded in its UI. If you switch models in LM Studio, click **Refresh** in the app so the dropdown matches.

---

## Manual entry (custom or non-standard runtimes)

If your runtime listens on a non-standard port, or you run an OpenAI-compatible server the app does not probe, click **Manual entry** and fill in:

- **Base URL (OpenAI-compatible)**, the chat-completions root. Examples:
  - `http://localhost:11434/v1` (Ollama default)
  - `http://localhost:1234/v1` (LM Studio default)
  - `http://192.168.1.50:11434/v1` (Ollama on another machine on your network)
- **Model**, the exact model id the runtime accepts. For Ollama this is the model tag (`llama3.2:latest`, `qwen2.5:7b`). For LM Studio it is whatever `GET /v1/models` lists.

Click **Save**. The (URL, model) pair is encrypted by your OS keychain the same way API keys are. The **Clear** button removes the saved configuration.

---

## Picking a model for an analysis

Select **Local LLM** in **Run with** on the Analyze page (and set **Mode** to **Quick analysis**). The model dropdown next to it lists the models your runtime reports right now. If your last-used model is no longer reported (for example the runtime is not running), it stays in the list marked *(last used, runtime offline)* so your choice is not silently changed. Picking a model in that dropdown updates the saved model shown in Settings.

---

## Cost behavior

Cost Guard treats local sessions as **$0**:

- They are **exempt** from the daily, weekly and monthly USD caps.
- They **still count** toward the optional sessions-per-day cap.

OpenAI sign-in sessions are treated the same way. See [cost-guard.md](cost-guard.md).

---

## Performance tips

- **Memory matters more than core count.** A model that does not fit in your free memory (RAM, or GPU memory with LM Studio offload) causes swapping, which turns seconds into minutes.
- **First-call latency** can be high while the runtime loads the model from disk. Run a test prompt in `ollama run` or LM Studio's chat first, then click **Analyze**.
- A Quick analysis runs twelve agents one after another, so total time is roughly twelve model responses. On slower hardware this can take several minutes. A smaller model (for example `llama3.2:1b`) is faster but weaker.

---

## Privacy

When **Local LLM** is the active provider, the analysis prompts (the ticker, the date, the price summary, headlines and social posts the app gathered, and the debate so far) are sent only to your local runtime. Nothing routes through OpenAI, Anthropic, OpenRouter, Gemini, xAI or MiniMax, and the model's responses stay on your machine.

The app still makes outbound requests for **data**, independent of the LLM provider: yfinance for prices and headlines, optionally Alpaca for market data and news, and StockTwits and Reddit for social posts in a Quick analysis. See [data-providers.md](data-providers.md) and [security-and-storage.md](security-and-storage.md) for the full list of network calls.

---

## Troubleshooting

**"No local runtime detected."** None of Ollama, LM Studio or llama.cpp's server is answering on its expected port. Check with `curl http://localhost:11434/v1/models` (Ollama) or `curl http://localhost:1234/v1/models` (LM Studio). If they answer but the app still does not detect them, check that the URL you can `curl` is exactly one of the defaults above, or use **Manual entry**.

**"Detection error: …"** The app's local engine could not run the probe. Quit and reopen the app, then click **Refresh**.

**The analysis fails with a model error.** Confirm the model is available:
- Ollama: `ollama list` should include the exact model id you saved, with its tag.
- LM Studio: the model must be loaded in the **Local Server** tab, not only downloaded.

**"Pro engine requires an API key or OpenAI OAuth."** You started a Full analysis with Local selected. Change **Mode** to **Quick analysis**, or pick a provider with a key.

**It takes much longer than with a hosted provider.** Local runtimes are limited by your CPU or GPU. Use a smaller model, or a hosted provider.

**The analysis is low quality.** Small local models (roughly under 7 billion parameters) often struggle with the multi-step reasoning a debate needs. Try a stronger model, or keep Local for testing and use a hosted model for the analyses you care about.

---

For the engine API contract, including the `/llm/local-runtimes` endpoint, see [docs/api.md](https://github.com/RBJGlobal/TradingAgentsLab-Pro/blob/main/docs/api.md).
