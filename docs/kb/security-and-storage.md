---
order: 140
---

# Security and Storage

*Where Trading Agents Lab Pro stores data on disk, how secrets are protected, and what to do when you change machines.*

> **For educational research and paper trading. This is not investment advice.**

---

## Summary

| What | Where | Format | Protection |
|---|---|---|---|
| API keys (LLM, Alpaca, Alpha Vantage), webhook list, Telegram bot token | `<userData>/secrets.json` (`llm:*`, `data:*`, `local:model`, `webhooks:configs`, `telegram:bot-token` entries) | Encrypted ciphertext | OS keychain (safeStorage) |
| OpenAI sign-in tokens | `<userData>/secrets.json` (`oauth:openai` entry) | Encrypted JSON blob | OS keychain (safeStorage) |
| Analysis history and transcripts | `<userData>/sessions.db` | SQLite | File-system permissions only |
| Watchlist tickers | same `sessions.db` (`watchlist` table) | SQLite | File-system permissions only |
| Cost Guard caps and spend record | same `sessions.db` | SQLite | File-system permissions only |
| HTML transcript exports | `<userData>/transcripts/` | HTML files | File-system permissions only |
| Full analysis memory notes | `~/.tradingagents/memory/trading_memory.md` | Markdown text | File-system permissions only |
| Engine process | spawned at runtime | n/a | Binds to 127.0.0.1 only; bearer token auth |

---

## The userData directory

Trading Agents Lab Pro keeps its files in one folder:

- **macOS:** `~/Library/Application Support/Trading Agents Lab Pro/`

You can find the exact path of the secrets file in **Settings → About → Secrets file**. Other small files in the same folder hold non-secret state: your acceptance of the educational-use notice (`consent.json`), window size and position (`window-state.json`), and app preferences (`preferences.json`).

---

## secrets.json: how key storage works

### Encryption model

Trading Agents Lab Pro uses Electron's `safeStorage` API, which delegates encryption to the operating system. On macOS that is Keychain Services, and the encryption key is bound to your macOS user account.

Plaintext is never written to disk. The `secrets.json` file contains:

```json
{
  "version": 1,
  "entries": {
    "llm:openai": {
      "hint": "…k3f9",
      "updatedAt": "2026-05-08T14:23:00.000Z",
      "cipher": "<base64-encoded encrypted bytes>"
    },
    "oauth:openai": {
      "hint": "oauth",
      "updatedAt": "2026-05-09T01:11:00.000Z",
      "cipher": "<base64-encoded JSON of {access, refresh, expires, email, accountId, planType}>"
    }
  }
}
```

The `hint` field (the last 4 plaintext characters of an API key, or `"oauth"` for sign-in blobs) is stored unencrypted solely so the Settings page can identify a row. It cannot be used to decrypt anything.

### Hard-fail design

If `safeStorage.isEncryptionAvailable()` returns false, the app refuses to store or read secrets rather than silently falling back to plaintext. Settings then shows a banner: *"Encryption backend unavailable on this OS."*

### If the file is damaged

If `secrets.json` cannot be read, the app renames it to `secrets.json.corrupt-<timestamp>.bak` in the same folder, starts with an empty file, and shows a notice in Settings with the backup path. You then re-enter your keys.

### Atomic writes

The `secrets.json` file is written atomically: the new content is written to a `.tmp` file first, then renamed over the original. This prevents partial writes.

### File permissions

`secrets.json` is written with mode `0600` (readable only by the file owner).

### Sign-in token lifecycle

OpenAI sign-in access tokens are short-lived (typically 1 hour). The sign-in service in the app's main process refreshes them automatically when they are within 60 seconds of expiring, using the stored refresh token. On every refresh, a new ciphertext blob is written atomically to `secrets.json`. The window fetches credentials immediately before each analysis starts, and they are not kept in the interface state beyond that. See [oauth.md](oauth.md).

### Where keys go

The app window can only talk to the local engine on `127.0.0.1` (its content security policy allows no other network address). Your LLM key is sent by the engine to the provider you selected, and your Alpaca keys only to Alpaca's data endpoints. The Alpha Vantage key goes only to Alpha Vantage.

---

## sessions.db: local analysis history

The engine writes every completed analysis to a SQLite file named `sessions.db`. This is **not encrypted** and is protected only by file-system permissions.

- **Location:** `~/Library/Application Support/Trading Agents Lab Pro/sessions.db`, next to `secrets.json`. This folder survives app updates, so your history, watchlist and Cost Guard spend record carry over from one version to the next.

> Before v1.1.7, the installed app kept this file inside the application bundle, so each update replaced it and history started over. v1.1.7 moved it out.

What is stored per analysis:

- Ticker and trade date
- Provider, model, auth mode (api_key / oauth), and which mode ran (Full or Quick)
- The full agent transcript
- The committee assessment (stance, conviction, bull strength, bear strength, risk level, reasoning)
- Token counts and estimated cost
- Created timestamp
- The price summary and headlines snapshot shown on the Analyze page

The database also holds your **Watchlist** tickers in a separate table, and the Cost Guard configuration and spend record.

If you want this data encrypted at rest, keep it on an encrypted volume (FileVault on macOS). There is no per-session encryption.

To reset history: quit the app, then delete `sessions.db` from the folder above, plus any `sessions.db-wal` and `sessions.db-shm` files beside it. The engine recreates it on next start. This also resets your Cost Guard spend record and watchlist. If you use the Telegram bot, its spend and chat-mode files (`telegram_spend.json`, `telegram_chat_modes.json`) sit in the same folder.

### HTML transcript exports

**Open in HTML** on a finished analysis writes a standalone HTML file to `<userData>/transcripts/` and opens it in your default browser. The files are kept, so you can bookmark, print or share them. Delete them from that folder when you no longer want them.

### Full analysis memory notes

A Full analysis records each completed run (ticker, date and the final decision text of the committee) in a Markdown file in your home folder, `~/.tradingagents/memory/trading_memory.md`. This is the upstream TradingAgents library's own decision log, and the app does not move it. The next Full analysis on the same ticker reads that log so the committee can take the earlier run into account. The file is plain text and is not encrypted. Delete it to clear that memory. Quick analysis does not use it.

---

## Engine: process isolation

The Python engine binds exclusively to `127.0.0.1` (loopback). It cannot be reached from the network. Every request requires a per-process bearer token that is generated at startup and passed to the app window through an internal channel. The token is never written to disk.

WebSocket authentication uses a query parameter (`?token=…`) because browsers cannot set Authorization headers on WebSocket connections. The token changes every time the engine restarts (that is, every time you launch the app).

---

## Update checks

The installed app can check for new versions automatically. This is the one network call the app itself initiates (separate from the data and LLM providers you configure with your own keys).

Trading Agents Lab Pro asks GitHub whether a newer version exists. Like any web request it reaches GitHub from your IP address and carries your system language. Up to Pro 1.1.8 the request also carried a random ID made for your install by the update library; we did not use it. From Pro 1.1.9 the request carries no ID for you or your install, and it does not send the version you have. When an update is downloaded, the download can name the version you have now.

- If a newer version exists, it downloads in the background and installs when you quit.
- The switch is **Settings → Updates → Automatically check for updates**. A manual **Check for updates** button is there too. You can turn the automatic check off.
- If the app cannot apply its update-check privacy protections, it refuses to check and shows "Update check not available. To update, download the latest version from tradingagentslab.ai."

---

## Machine migration

Because `safeStorage` encryption is machine- and user-bound, you cannot copy `secrets.json` to a new machine and have it work. The ciphertext cannot be decrypted outside the original machine and user.

`sessions.db` is portable. Copy the file to the new machine and the History page will show your previous analyses. (It contains transcripts, not credentials, so there is no decryption issue.)

### Recovery procedure

1. On your new machine, install Trading Agents Lab Pro from the DMG (see [getting-started.md](getting-started.md)).
2. Open Settings and re-paste each API key from your password manager or the provider's dashboard. Re-add your webhooks.
3. If you used OpenAI sign-in, connect again with the **Connect** button.
4. Optionally, copy `sessions.db` from the old machine (location above) to keep your history. Quit the app on both machines first.

There is no automated export or import of secrets. Manual re-entry is the migration path.

---

## What is never stored

- Plaintext API keys: never written anywhere.
- Engine bearer tokens: generated at runtime, held in memory only.
- Plaintext sign-in tokens: only the encrypted blob reaches disk; in-memory access tokens are dropped between analyses.
- Telemetry: Trading Agents Lab Pro sends no analytics, no error reports and no usage data anywhere. There are no accounts.

---

## Further reading

- [Configuring LLM providers](configuring-llm-providers.md), how to add and manage keys
- [OAuth](oauth.md), token lifecycle and refresh model
- [Troubleshooting](troubleshooting.md), encryption unavailable and damaged secrets file
- [Getting started](getting-started.md), initial setup
