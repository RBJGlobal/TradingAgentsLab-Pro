---
order: 150
---

# Troubleshooting

*Common problems in Trading Agents Lab Pro and how to fix them.*

> **For educational research and paper trading. This is not investment advice.**

---

## Engine problems

### "Engine starting" never clears

The Analyze page shows "Engine starting, please wait. Python sidecar is coming online." while the engine starts, and the **Engine** pill at the top shows "starting…". This normally clears within a few seconds of launch.

If it does not:

1. Click the **⏻** button at the top right and choose **Restart** ("Relaunch with a fresh engine").
2. If that does not help, choose **Shut down** from the same menu, then open the app again from the Applications folder.
3. If the Analyze page says "Engine could not start after several retries" followed by a message, try a restart once more, then use **Help → Contact Support** and include that message.

---

## Analysis problems

### The analysis runs but shows a stub or canned debate

The **Run with** dropdown on the Analyze page shows **Stub debate (no LLM configured)** when no provider is set up, and the helper text under the Analyze button says "Stub debate. Paste an LLM key in Settings to switch to live agents." The stub debate is free, uses placeholder content, and its reasoning text says "Stub canned debate" so it is easy to recognize.

To switch to live agents:

1. Open **Settings → LLM Providers** and add a key for OpenAI, Anthropic, OpenRouter, Google Gemini, xAI Grok or MiniMax (or sign in with OpenAI, or pick a local runtime for Quick analysis).
2. Go back to Analyze and check that **Run with** shows your provider (not "(configure in Settings)").
3. If the provider is listed but you still get a stub, use **Replace** on that key in Settings to save it again.
4. If **Settings → OpenAI account (OAuth)** shows "Connected" but runs fall back to a stub or fail, click **Disconnect** and **Connect** again to refresh the sign-in.

### A Full analysis takes a long time

A Full analysis runs the whole research graph, with many model calls in sequence, and the run shows "Typically 8 to 15 minutes." Time depends on the provider, the model, the debate and risk round counts and the number of analysts enabled under **Settings → Analysis**. A Quick analysis finishes in about a minute. You can press **Stop** at any time. If you want a faster look, switch **Mode** on the Analyze page to **Quick analysis**.

### "Analysis stopped" notice instead of a committee assessment

A run can stop before it reaches an assessment. The notice says why:

- **A Cost Guard stop:** "Stopped: This run reached your Cost Guard ... cap" means the run hit a daily, weekly or monthly cap partway through. Raise the cap under **Settings → Cost Guard**, or use Override when starting the run. "Stopped: This run spent ..., about three times its estimate" means Cost Guard ended a run it judged to be running away from its estimate; check the models and round counts in Settings and try again. What the run spent so far still counts toward your totals. See [cost-guard.md](cost-guard.md).
- **A token cap:** "Analysis stopped: token cap of N reached" means the optional **Max tokens per run** in **Settings → Analysis** was reached. Raise it, or clear it to rely on the Cost Guard caps.

A stopped run produces no assessment and fires no webhooks.

### "Analysis failed" notice

The notice shows the error from the run, and no assessment was produced. Common causes are an invalid or expired key, a model name your account cannot use, or a provider outage. Check the key and model for the provider under **Run with** and try again. A Full analysis only works with an API key or OpenAI sign-in; if you picked a local runtime (Ollama or LM Studio), switch **Mode** to **Quick analysis**.

### "Budget cap reached" or "Session rate cap reached"

Cost Guard checked the estimated cost of the run before starting and found it would cross one of your caps. Choose **Cancel**, adjust the caps under **Settings → Cost Guard**, or choose **Override and continue** (enabled after a short countdown) for this one run. See [cost-guard.md](cost-guard.md).

### OpenAI sign-in: expired, rate limited or free-tier notice

- **"Your ChatGPT sign-in has expired."** Click **Sign in again** in Settings, or add an OpenAI API key to use instead.
- **A rate-limit error (429).** You have exceeded your ChatGPT plan's rate window. Wait a while, or use an OpenAI API key for the rest of the day. See [oauth.md](oauth.md).
- **A free-tier warning appears.** Free ChatGPT accounts have unreliable Codex routing: many models hang or return errors. Add an OpenAI API key and pick it under **Run with**.

### A stream error appears mid-analysis

The connection between the app window and the engine closed unexpectedly, for example because the engine was stopped by the system. Click **Analyze** again to start a new run. If the error recurs, choose **⏻ → Restart**.

### The analysis finishes instantly with no agent messages

The stream opened and closed in under a second. This usually means the engine was restarted while the window still held an old connection. Choose **⏻ → Restart** and try again.

---

## Data problems

### "Yahoo Finance returns no data" or the data summary strip is absent

The price summary strip is absent when no price data came back. This happens when:

- **Unknown ticker:** Yahoo Finance has no data for that symbol. Check the spelling.
- **Weekend or holiday date:** the date you entered falls on a non-trading day. The engine anchors to the most recent prior trading day, but if the whole lookback window has no bars the strip stays empty. Try a weekday.
- **Future date:** the date picker is capped at today.
- **Network issue:** Yahoo Finance can rate-limit or time out. Wait a minute and try again.

The analysis still runs when data is unavailable; the agents fall back to more general language instead of citing specific prices.

### Yahoo Finance news headlines are empty

This is normal for some tickers or at certain times of day. Yahoo Finance's news feed does not guarantee coverage for every ticker. The analysis runs without the News card.

For fuller coverage, connect a free Alpaca account under **Settings → Data Providers**. News then comes from Alpaca's Benzinga feed, for both the News card and the News analyst in a Full analysis (with **Settings → Analysis → News source** on Auto or Alpaca). See [data-providers.md](data-providers.md#news-sources).

### Alpaca shows "Key rejected" or "Not checked"

"Key rejected" means Alpaca refused the Key ID and Secret, usually because the pair was regenerated or deleted. Create a new pair on the Alpaca dashboard and paste both values again. "Not checked" means Alpaca could not be reached, so the keys could not be tested; use **Check again**. While Alpaca is rejected, analyses run without Alpaca data and a notice says so. See [data-providers.md](data-providers.md).

### A Full analysis lacks social or fundamentals content

Only the analysts ticked under **Settings → Analysis → Analysts** run in a Full analysis, and the default is Market only. Tick the others you want. The Settings note says the News, Social and Fundamentals analysts use an Alpha Vantage key, which you can add under **Settings → Data Providers**.

---

## Settings and secret storage problems

### "Encryption backend unavailable on this OS"

This banner appears on the Settings page when the operating system's encrypted credential store cannot be used. The app refuses to store secrets in plaintext, so this is deliberate. On macOS it should not occur; quit and reopen the app, and if it persists use **Help → Contact Support**.

### "Encrypted secrets file recovered"

If `secrets.json` cannot be read, the app moves it aside to `secrets.json.corrupt-<timestamp>.bak`, starts with an empty file, and shows this notice with the backup path. Re-enter your API keys and webhooks. See [security-and-storage.md](security-and-storage.md).

---

## Webhook problems

The **Webhooks** card under the debate lists each receiver as fired, filtered or failed.

- **filter did not match:** the assessment's stance or conviction did not meet that webhook's filter. Loosen the filter under **Settings → Webhooks**.
- **failed with an HTTP status:** the receiver answered with an error. For Telegram, a 400 usually means a wrong Chat ID, or that you have not yet sent your bot a first message. A 401 or 404 usually means a wrong token or URL.
- **failed with timeout:** the receiver took longer than 5 seconds. There is no retry, so run the analysis again once the receiver is healthy.

See [webhooks.md](webhooks.md).

---

## Update problems

- **"Update check not available. To update, download the latest version from tradingagentslab.ai."** The app could not apply its update-check privacy protections, so it refuses to check. Download the latest DMG from the site and install it over the current app.
- **No update appears.** Open **Settings → Updates** and press **Check for updates**. An update that has downloaded installs when you quit, or press **Restart & install**.

---

## Further reading

- [Getting started](getting-started.md), first-time setup
- [Security and storage](security-and-storage.md), secrets.json location and recovery
- [How it works](how-it-works.md), stub mode versus live analysis
- [Cost Guard](cost-guard.md), caps, estimates and overrides
