# engine — TradingAgentsLab Python sidecar

FastAPI server that wraps the `tradingagents` multi-agent core. The Electron
desktop app spawns this process on startup, reads `{port, token}` from stdout,
and routes all analysis traffic through it.

## Run (dev)

```bash
# One-time: create venv with Python 3.13
~/.local/share/uv/python/cpython-3.13.5-macos-aarch64-none/bin/python3.13 -m venv .venv

# Install
.venv/bin/pip install -r requirements.txt

# Run
.venv/bin/python -m engine
```

On startup the process prints one JSON line to stdout, e.g.

```json
{"port": 51234, "token": "abc..."}
```

Then waits for HTTP / WebSocket clients on `127.0.0.1:<port>`.

## Endpoints

- `GET /health` — sanity ping. Bearer auth.
- `POST /analyze` — one-shot analysis. Bearer auth. Phase 2 returns a stub.
- `WS /stream?token=<token>` — live multi-agent debate. Phase 2 emits a
  canned sequence over ~6 seconds. Phase 3+ wires the real `tradingagents`
  pipeline behind this.

## Phase status

- ✅ Phase 2 — FastAPI scaffold + canned debate
- ⚪ Phase 3 — wire to Electron renderer (separate workstream)
- ⚪ Phase 4+ — replace stub LLM/data/broker providers with real ones
