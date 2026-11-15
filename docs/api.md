# TradingAgentsLab Engine API

> **Audience:** Claude or human picking up the engine sidecar contract cold. Used by `desktop/src/lib/engine-client.ts` from the renderer; no other clients exist yet.

The engine is a FastAPI sidecar bound to `127.0.0.1:<random-port>` with a per-process bearer token. The Electron main process spawns it on `app.whenReady` and parses `{port, token}` from the first stdout line. Every endpoint requires bearer auth. The renderer obtains the bearer via the `tradingAgentsLab.getEngineHandshake()` contextBridge.

If anything in this doc disagrees with `engine/server.py`, treat the source as authoritative and update this doc.

## Authentication

| Transport | Mechanism |
|---|---|
| HTTP | `Authorization: Bearer <token>` header on every request. 401 otherwise. |
| WebSocket | `?token=<token>` query parameter (browsers can't set headers on `WebSocket`). Server closes with code `1008 invalid token` on mismatch before `accept()`. |

CORS uses `allow_origins=["*"]` (see `engine/server.py`). This is intentional and not a security boundary: the engine binds to loopback only and every endpoint is bearer-gated, while the renderer's origin is `null` (Electron `file://`) in production and the Playwright e2e harness also loads `file://`, so a wildcard is the only value that works across both. WebSocket is not subject to CORS.

## HTTP endpoints

### `GET /health`

```json
{
  "ok": true,
  "version": "0.0.1",
  "uptime_seconds": 12.4,
  "engine_state": "ready",
  "data_provider": "yfinance",
  "live_supported": true,
  "live_providers": ["anthropic", "gemini", "openai", "openrouter"],
  "live_default_models": {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-haiku-4-5",
    "openrouter": "openai/gpt-4o-mini",
    "gemini": "gemini-2.0-flash"
  },
  "storage_path": "/Users/jay/Projects/TradingAgents/data/sessions.db"
}
```

`engine_state` describes engine *capability*, not the most recent session: it is `"ready"` whenever the server is up. Whether a given session ran a stub or a live debate is reported per-session in the `session.complete` event (see WS contract below). `data_provider` reports the active `BaseDataProvider.name`. `live_supported` indicates the engine can run real-LLM debates when given a `provider_config`. `live_providers` is the allowlist the engine accepts; `live_default_models` shows the per-provider model the engine assumes when `provider_config` arrives without an explicit `model` field. `storage_path` reports where the engine writes persisted sessions: `<repo>/data/sessions.db` by default, overridable via the `TAL_SESSIONS_DB` env var. The packaged desktop app sets that variable, so installed builds report `<userData>/sessions.db`.

### `GET /data/summary?ticker=<X>&trade_date=<YYYY-MM-DD>`

Returns a compact view of recent OHLCV data anchored on `trade_date`. Response shape (`QuoteSummary` in `engine/data_providers.py`):

```json
{
  "ticker": "NVDA",
  "trade_date": "2026-05-08",
  "as_of": "2026-05-07",
  "last_close": 211.5,
  "period_open": 177.16,
  "period_high": 216.83,
  "period_low": 173.66,
  "period_change_pct": 19.38,
  "avg_volume": 147571146.0,
  "sessions": 24,
  "source": "yfinance",
  "asset_class": "equity"
}
```

| Status | Meaning |
|---|---|
| 200 | Summary available |
| 404 | `DataUnavailable` — provider returned no rows (unknown ticker, all-future date range, etc.) |
| 502 | Other provider error (network, rate limit, parse failure) |

### `GET /data/news?ticker=<X>&limit=<N>` (default `limit=5`, range `[1, 20]`)

```json
{
  "ticker": "NVDA",
  "source": "yfinance",
  "headlines": [
    {
      "title": "...",
      "publisher": "Yahoo Finance Video",
      "pub_date": "2026-05-07T21:04:15Z",
      "url": "https://finance.yahoo.com/...",
      "summary": "..."
    }
  ]
}
```

Empty `headlines` list is a valid 200 response — never 404. 502 on provider errors.

### `POST /analyze`

Phase 2/3 stub — returns a deterministic HOLD decision regardless of input.

```jsonc
// Request
{ "ticker": "NVDA", "trade_date": "2026-05-08" }

// Response
{
  "ok": true,
  "ticker": "NVDA",
  "trade_date": "2026-05-08",
  "decision": {
    "action": "HOLD",
    "confidence": 0.5,
    "reasoning": "Stub response — engine not yet connected to tradingagents core."
  },
  "agents": []
}
```

Live-LLM `POST /analyze` is intentionally not wired today: the streaming WS path is the canonical entrypoint for real debates, and supports `provider_config`. A one-shot `POST /analyze` that ran an OpenAI session would burn ~$0.005 per request without giving the user the streaming UX. When/if a non-streaming caller appears, this endpoint will accept the same `provider_config` shape as the WS start frame.

### `GET /sessions?limit=<N>&ticker=<X>`

Lists recently-completed debates, newest first. `limit` defaults to 50 (max 500). `ticker` is optional and case-insensitive. Returns a list of *summaries* — no event payload, no transcript. Use `GET /sessions/{id}` to inflate one.

```jsonc
{
  "sessions": [
    {
      "id": "019e0a0e95c1-8403736e",     // ULID-like, lexicographically sortable
      "ticker": "NVDA",
      "trade_date": "2026-05-08",
      "decision_action": "HOLD",
      "decision_confidence": 0.55,
      "decision_reasoning": "...",
      "live": false,                     // false for stub, true for real-LLM
      "provider": null,                  // populated when live
      "model": null,                     // populated when live
      "input_tokens": null,
      "output_tokens": null,
      "estimated_cost_usd": null,
      "created_at": "2026-05-09T00:06:28Z"
    }
  ]
}
```

### `GET /sessions/{id}`

Returns the full detail for a single session, including the inflated `events` array (every WS event the renderer received during the original stream). Used by the History detail view to replay a past debate.

```jsonc
{
  "id": "019e0a0e95c1-8403736e",
  "ticker": "NVDA",
  "trade_date": "2026-05-08",
  "decision_action": "HOLD",
  "decision_confidence": 0.55,
  "decision_reasoning": "...",
  "live": true,
  "model": "gpt-4o-mini",
  "input_tokens": 7401,
  "output_tokens": 2384,
  "estimated_cost_usd": 0.0025,
  "created_at": "2026-05-09T00:06:28Z",
  "events": [
    { "type": "session.start", "ticker": "NVDA", "trade_date": "2026-05-08" },
    { "type": "data.summary", "...": "..." },
    { "type": "agent.message", "agent": "technical_analyst", "...": "..." },
    "..."
  ]
}
```

| Status | Meaning |
|---|---|
| 200 | Session found |
| 404 | No session with that id |

### `DELETE /sessions/{id}`

Deletes a single session row. Returns `{"deleted": true, "id": "..."}` on success, 404 if the id doesn't exist. CORS-allowed for the renderer origin (`DELETE` is in the `Access-Control-Allow-Methods` list).

### Session persistence model

Persistence is **strictly post-stream**: the engine captures the WS event sequence in memory while it streams, and writes a single SQLite row only after `session.complete` is sent (and only when one is sent — aborted streams via the renderer's Stop button do *not* persist). Failures to write are logged to stderr and silently ignored — the user already saw the debate, so persistence is best-effort, not contract.

Storage backend: SQLite at `<repo>/data/sessions.db` (dev) with WAL mode + `PRAGMA synchronous=NORMAL`. Override the path with the `TAL_SESSIONS_DB` env var. The packaged desktop app sets it to `<userData>/sessions.db` so history survives app updates (see `desktop/electron/sessions-db.ts`; before v1.1.7 the file lived inside the app bundle and was replaced on every update). The DB file is gitignored. Schema version 1; older schemas are upgraded in place by `_ensure_initialized()`, newer schemas refuse to write (the engine will refuse to clobber a file from a future version).

### `GET /watchlist`

Lists the user's saved watchlist tickers, newest-first by `added_at`. Same SQLite file as sessions; same schema-version contract.

```jsonc
{
  "watchlist": [
    {
      "ticker": "NVDA",
      "added_at": "2026-05-09T00:19:31Z",
      "note": "watch earnings on the 23rd"   // nullable
    }
  ]
}
```

### `POST /watchlist`

```jsonc
// Request
{ "ticker": "NVDA", "note": "..." }      // note is optional, max 200 chars

// 200 response — newly created entry
{ "ticker": "NVDA", "added_at": "...", "note": "..." }
```

| Status | Meaning |
|---|---|
| 200 | Created |
| 400 | Empty or whitespace-only ticker (after `.strip()`). |
| 409 | Ticker already on the watchlist. |
| 422 | Ticker fails Pydantic validation (length, type). |

### `DELETE /watchlist/{ticker}`

```jsonc
{ "removed": true, "ticker": "NVDA" }
```

| Status | Meaning |
|---|---|
| 200 | Removed |
| 404 | Ticker not on the watchlist |

CORS-allowed for the renderer origin (`DELETE` is in `Access-Control-Allow-Methods`).

### Cost Guard endpoints

| Endpoint | Purpose |
|---|---|
| `GET /cost-guard/state` | Current spend (`daily_usd`, `weekly_usd`, `monthly_usd`, `sessions_today`) and config |
| `PUT /cost-guard/config` | Patch caps and the enable flag (only the fields sent change) |
| `POST /cost-guard/check` | Dry run: would this run be allowed? No reservation is created |
| `POST /cost-guard/reserve` | Atomic check and reservation; returns a `reservation_id` or HTTP 402 |

New databases are seeded with a $5.00 daily, $15.00 weekly and $45.00 monthly cap and no sessions-per-day cap. Existing databases keep their configured caps.

#### `POST /cost-guard/check` and `POST /cost-guard/reserve`

```jsonc
{
  "model": "claude-sonnet-4-6",   // the run's primary (deep) model
  "auth_kind": "api_key",         // api_key | oauth | local
  "max_tokens": 400,              // simplified-debate budget; unused for Pro
  "provider": "anthropic",        // optional; inferred from the model id when absent
  "override": false,              // reserve only: run anyway past a cap
  // Optional. Present for a Trading Agents Lab Pro full-graph run.
  "pro": {
    "deep_think_llm": "claude-sonnet-4-6",
    "quick_think_llm": "claude-sonnet-4-6",
    "selected_analysts": ["market", "social", "news", "fundamentals"],
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1
  }
}
```

Without `pro`, the estimate is the simplified debate's worst case (12 agents at `max_tokens`). With `pro`, it is the Pro full-graph estimate (`cost_guard.pro_reservation_estimate`): per-node token budgets calibrated to about 1.4x a measured default run, the research manager and portfolio manager priced at `deep_think_llm` and every other node at `quick_think_llm`, input growing with each extra debate or risk round, billed output scaled 2.5x for models that think by default, plus the post-graph thesis-scoring call. Missing or empty `selected_analysts` means all four. The WebSocket auto-reserve builds the same `pro` block from the start frame's `pro_config`, so both paths give the same number for the same run.

Every per-token model is priced, never $0: an exact rate row, then the row for a dated id (`claude-haiku-4-5-20251001` uses the `claude-haiku-4-5` row), then an OpenRouter price learned at runtime, then the vendor's own row for an OpenRouter id, then a family ceiling (for example $15 / $75 per million tokens for an unrecognised Claude or an unknown vendor). OAuth and local runs are $0.

`check` returns `{allow, over_dimension, override_available, current, config, est_reservation_usd}`. `reserve` returns:

```jsonc
{
  "reservation_id": "0193...-a1b2c3d4",
  "est_cost_usd": 1.3073,
  "expires_at": "2026-11-14T18:00:00Z",
  "auth_kind": "api_key",
  "override": false,
  // Mid-run USD stop stored on the reservation (null for OAuth / local).
  "usd_limit": 5.0,
  "limit_reason": "cap",          // "cap" | "runaway" | null
  "limit_dimension": "daily"      // "daily" | "weekly" | "monthly" | null
}
```

`usd_limit` is decided at reserve time. For a normal run it is the smallest headroom left under any enabled USD cap (cap minus completed spend and other live reservations in that window). For an override run, or when Cost Guard is disabled or no USD cap is enabled, it is 3x `est_cost_usd` (a runaway stop). The Pro engine reads it at run start and ends the run with `run.cost_cap` before a call that could cross it.

Reservations expire after 15 minutes, or 60 minutes when `pro` is present. A blocked reserve returns HTTP 402 with `detail: {error: "cost_guard_blocked", over_dimension, spend, config, est_cost_usd}`.

What counts as spend in each window: completed sessions, live reservations at their estimate, and the real cost of runs that ended early (cost cap, token cap, error, or a stopped stream), which write no session row.

## WebSocket endpoint

### `WS /stream?token=<token>`

Bidirectional channel for streaming the multi-agent debate.

**Client opens, sends a start frame, server streams events, server closes 1000.** No keepalive ping/pong is in scope for v1.

#### Client → server: start frame

Sent by the client immediately after `open`:

```jsonc
{
  "ticker": "NVDA",
  "trade_date": "2026-05-08",
  // Optional. When present, the engine runs a real-LLM debate via the
  // configured provider; when absent, it runs the canned stub debate.
  "provider_config": {
    "provider": "openai",        // openai | anthropic | openrouter | gemini
    "auth": {
      "type": "api_key",         // "api_key" | "oauth"
      "api_key": "sk-…"
    },
    "model": "gpt-4o-mini",      // optional, defaults to gpt-4o-mini
    "max_tokens": 400            // optional, defaults to 400, hard cap
  }
}
```

`auth` is a discriminated union — the engine attaches whichever Bearer token comes out of it to the upstream chat-completions call. Two shapes:

```jsonc
// API key (all providers)
{ "type": "api_key", "api_key": "sk-…" }

// OAuth (OpenAI only — Anthropic OAuth is banned by their TOS)
{ "type": "oauth", "access": "…", "refresh": "…", "expires": 1700000000 }
```

Backwards-compat: the legacy shape `{api_key: "..."}` at the top level (no `auth` field) is still accepted and converted internally to `{type: "api_key", api_key}`. New renderer builds always send the discriminated union.

**Optional fields on the start frame:**

- `reservation_id` — pre-reserved CostGuard slot (renderer-side reservation succeeded). Engine skips its server-side auto-reserve when present.
- `data_config` — per-stream data provider override, e.g. `{provider: "alpaca", key_id, secret}`. Absent → engine uses its default (yfinance unless module-level swap).
- `webhooks` — list of `WebhookConfig` to fire after `session.complete`. Schema:
  ```jsonc
  {
    "id": "wh1",
    "name": "Telegram me",
    "url": "https://api.telegram.org/bot<TOKEN>/sendMessage",
    "kind": "telegram",        // "telegram" | "slack" | "discord" | "generic"
    "secret": "shh",           // optional — only used for kind=generic (HMAC-SHA256)
    "filter": {                // optional, defaults to fire-on-everything
      "actions": ["BUY", "SELL"],     // empty array = all
      "min_confidence": 0.7            // 0..1, inclusive floor
    }
  }
  ```
- `telegram_chat_ids` — `{webhook_id: chat_id}` map, since Telegram chat_id isn't part of the bot-API URL.

The server reads exactly one start frame, then becomes write-only. If `provider` is not in the allowlist OR `auth.type` is unrecognised OR an OAuth `auth` arrives for a non-OpenAI provider, the engine falls through to the stub path rather than erroring — this lets the renderer ship UI-side support for new providers ahead of engine-side wiring.

#### Server → client: event stream

Each line is a JSON object with a `type` discriminator. Order is deterministic.

##### 1. `session.start`

```json
{ "type": "session.start", "ticker": "NVDA", "trade_date": "2026-05-08" }
```

##### 2. `data.summary` (best-effort, omitted if data fetch fails)

Same shape as the `GET /data/summary` body, with a `type: "data.summary"` discriminator added.

##### 3. `news.headlines` (best-effort, omitted if no headlines)

Same shape as `GET /data/news` body, with `type: "news.headlines"` discriminator added.

##### 4. `agent.message` × N

```json
{
  "type": "agent.message",
  "agent": "technical_analyst",
  "phase": "analysts",
  "content": "[STUB · yfinance] ..."
}
```

Phase canonical values: `"analysts" | "researchers" | "trader" | "risk"`. Agents inside each phase, in order:

| Phase | Agents |
|---|---|
| `analysts` | `technical_analyst`, `fundamental_analyst`, `news_analyst`, `sentiment_analyst` |
| `researchers` | `bull_researcher`, `bear_researcher`, `research_manager` |
| `trader` | `trader` |
| `risk` | `risk_aggressive`, `risk_conservative`, `risk_neutral`, `portfolio_manager` |

##### 5. `phase.transition`

```json
{ "type": "phase.transition", "from": "analysts", "to": "researchers" }
```

Emitted between phases.

##### 6. `cost.usage` × N (live only)

```jsonc
{
  "type": "cost.usage",
  "input_tokens": 1840,
  "output_tokens": 612,
  "est_cost_usd": 0.0012,
  "free": false
}
```

Emitted immediately after every `agent.message` during a live debate so the renderer can tick a real-time spend pill without waiting for `session.complete`. Token counts are running totals across the session, not per-message deltas. `free=true` for OAuth subscription runs and local-LLM runs — both bill at $0 and `est_cost_usd` is `0.0` regardless of token count (the renderer should render "subscription" / "on-device" rather than the literal zero). Stub-mode sessions never emit this event.

##### 7. `webhook.report` (live + stub, only when webhooks configured)

```jsonc
{
  "type": "webhook.report",
  "results": [
    { "id": "wh1", "name": "Telegram me", "status": "fired", "http_status": 200 },
    { "id": "wh2", "name": "Slack channel", "status": "filtered" },
    { "id": "wh3", "name": "My CF Worker", "status": "failed", "error": "timeout" }
  ]
}
```

Emitted ONCE after `session.complete`, only when the start frame carried a non-empty `webhooks` list. Each result has `status: 'fired' | 'filtered' | 'failed'`. `fired` includes `http_status` (2xx); `failed` includes `http_status` (non-2xx) OR `error` (network/timeout/exception). `filtered` means the receiver's action/confidence filter excluded this decision — not a failure.

**Security**: results NEVER carry the webhook URL. Telegram/Discord URLs embed bot tokens. Receivers are identified by `id` + `name` only.

##### 8. `session.complete`

```jsonc
{
  "type": "session.complete",
  "ticker": "NVDA",
  "trade_date": "2026-05-08",
  "decision": {
    "action": "HOLD",   // BUY | SELL | HOLD
    "confidence": 0.55, // 0..1
    "reasoning": "..."
  },
  // Live-only fields — present when the session ran via a real LLM.
  // Stub-mode session.complete carries only the four fields above.
  "live": true,
  "model": "gpt-4o-mini",
  "input_tokens": 7401,
  "output_tokens": 2384,
  "estimated_cost_usd": 0.0025
}
```

When `provider_config` was supplied in the start frame, the engine populates `live`, `provider`, `model`, `input_tokens`, `output_tokens`, and `estimated_cost_usd`. The renderer uses these to render a "Live · provider · model" badge on the decision card and to log a per-session cost estimate. Cost is calculated using local rate tables (`engine/llm_providers.py:_COST_PER_M_TOKENS`) and is **never** authoritative: it's a budgeting hint, not a billing record. A model with no rate row (an OpenRouter id, a new model) is priced from a high family estimate, never 0.0; see Cost Guard endpoints.

##### 9. Pro terminal events: `run.cost_cap`, `run.token_cap`, `run.error`

A Trading Agents Lab Pro full-graph run can end without `session.complete`. The server still closes with `1000`, so the renderer detects these events. Nothing is written to History, but the run's real cost so far is billed to the Cost Guard totals.

```jsonc
// Cost Guard's mid-run USD stop (see usd_limit under Cost Guard endpoints).
{
  "type": "run.cost_cap",
  "used_usd": 0.87,           // spent so far, at the same rates as the ledger
  "limit_usd": 0.9,
  "reason": "cap",            // "cap" | "runaway" (override / uncapped, 3x estimate)
  "dimension": "daily",       // which cap set the limit; null for "runaway"
  "input_tokens": 151200,
  "output_tokens": 25800,
  "message": "Stopped: this run reached your Cost Guard daily cap after spending $0.87. Raise the cap in Settings, Cost Guard, or use Override."
}

// The optional per-run token cap was reached.
{ "type": "run.token_cap", "used": 150321, "cap": 150000, "message": "..." }

// A graph node raised.
{ "type": "run.error", "error": "..." }
```

The USD stop is checked before each LLM call: when spent so far plus the largest single call seen so far could cross `limit_usd`, the call is refused and the graph halts, so a run overshoots by at most one call. The post-graph thesis-scoring call is skipped (strength bars left empty) when it could cross the limit. During a Pro run, `cost.usage.est_cost_usd` carries the running cost at those same rates.

##### Server close

Server calls `ws.close(code=1000)` after `session.complete` is sent. The renderer also treats `1005` (no-status) as clean for edge timing where the server's close frame isn't observed before the socket teardown.

#### Cancellation

Client can call `WebSocket.close()` at any time; the server's `WebSocketDisconnect` handler returns cleanly without further frames. The renderer's `streamDebate()` wrapper exposes a `{close, done}` handle for this.

## Process model

### Spawn (Electron main → engine)

```
$REPO/desktop/electron/engine-runner.ts
  spawn("$REPO/engine/.venv/bin/python", ["-m", "engine"], { cwd: "$REPO" })
  └── child.stdout — first line is JSON {port, token}; subsequent lines are uvicorn logs
  └── child.stderr — uvicorn logs (teed to main process console with [engine] prefix)
```

`cwd: $REPO` is required so `python -m engine` resolves the `engine` package via `sys.path[0]`.

### Handshake (renderer → main → engine)

The Electron main process awaits `child.stdout.once('data')`, parses it once, and caches the resulting `Promise<EngineHandshake>`. The renderer fetches the cached handshake via the IPC channel `engine:get-handshake`, so the renderer never sees uvicorn's logs.

### Teardown

`stopEngine()` is called from `before-quit` and `window-all-closed`. It sends `SIGTERM` to the child. uvicorn handles the signal and shuts down the asyncio loop cleanly.

## Smoke test

`tools/dev-smoke.sh [TICKER] [TRADE_DATE]` runs all the above contract checks end-to-end without involving Electron or the renderer. Use it to rule the backend out when the UI isn't streaming, or as a fresh-session sanity check after a reboot.

## Out of scope (intentional gaps)

- Per-call provider override from the renderer — the active provider is currently picked by `PROVIDER_PRIORITY` order in the renderer (first-found-key wins). A user-facing "Run with: …" dropdown is a future UX win.
- DeepSeek / Mistral / xAI / others — not wired today. The allowlist (`engine/llm_providers._ALLOWED_PROVIDERS`) is the source of truth; unsupported providers fall through to the stub rather than erroring, so the renderer can ship UI ahead of engine support.
- Token-level streaming — each agent's full response is sent as a single `agent.message` event. Token-by-token streaming is a future protocol upgrade and would gate on a `agent.message.delta` event variant.
- Cross-session search / export / sharing — persistence is per-row only. Future.
- Authentication beyond bearer — sidecar is `127.0.0.1`-bound; no remote callers.
- Rate limiting / quotas — `max_tokens` and `MAX_AGENTS_PER_SESSION` are the only hard caps. The engine logs estimated cost per session to stderr, and the renderer surfaces it on the decision card; there is no enforced spend ceiling beyond the per-call cap.
- Versioned protocol — single canonical version today. When it changes, the start frame will gain a `protocol_version` field and the server will reject mismatches with close code `1008`.
