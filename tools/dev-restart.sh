#!/usr/bin/env bash
#
# tools/dev-restart.sh — clean restart of the dev stack from a detached
# child process. Used by the Electron main process when the user clicks
# Restart in the app's titleBar dropdown (in dev mode).
#
# In dev mode `app.relaunch()` doesn't work: vite-plugin-electron exits
# Vite when its child Electron exits, but `app.relaunch()` only respawns
# Electron — the new Electron loads from a dead localhost:5173. This
# script handles the full dance:
#
#   1. Wait briefly so the calling Electron has time to fully exit
#   2. Kill any leftover vite/electron/engine from the old session
#      (handles the case where vite was still alive when Electron quit)
#   3. Brief settle pause so the OS releases ports
#   4. Spawn a fresh `npm run dev` from the repo root
#
# Spawned detached + stdio=ignore by the calling main process so this
# script outlives the Electron quit and orchestrates the clean restart.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Step 1 — let the caller's Electron exit cleanly first.
sleep 2

# Step 2 — kill anything left over from the old session. Pattern matches
# our specific repo path so we don't disturb other Electron apps.
pkill -f "TradingAgents/desktop/node_modules/.bin/vite" 2>/dev/null || true
pkill -f "TradingAgents/desktop/node_modules/electron/dist/Electron" 2>/dev/null || true
pkill -f "engine/.venv/bin/python -m engine" 2>/dev/null || true

# Step 3 — short settle so the OS releases port 5173 + the engine port.
sleep 1

# Step 4 — fresh dev stack.
cd "$REPO_ROOT"
exec npm --prefix desktop run dev
