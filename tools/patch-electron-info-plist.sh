#!/usr/bin/env bash
#
# tools/patch-electron-info-plist.sh — overrides "Electron" with our display
# name in the vanilla Electron.app's Info.plist so the macOS dock tooltip,
# Force Quit list, and Spotlight all show the right app name in dev mode.
#
# Why this exists: in dev mode (`npm run dev`), vite-plugin-electron launches
# Electron via `node_modules/electron/dist/Electron.app`. macOS reads the
# bundle name from that .app's Info.plist BEFORE our main.ts runs, so the
# runtime `app.setName('Trading Agents Lab')` call only updates the menu
# bar — not the dock tooltip. Patching CFBundleName + CFBundleDisplayName
# at install time fixes the remaining surfaces.
#
# Production builds (Phase 7 electron-builder) generate a fresh .app
# bundle with the correct Info.plist; this script is a dev-mode-only
# workaround. Wired as a `postinstall` in desktop/package.json so it
# re-applies after every `npm install` (which would otherwise clobber
# the patch).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ELECTRON_APP="$REPO_ROOT/desktop/node_modules/electron/dist/Electron.app"
PLIST="$ELECTRON_APP/Contents/Info.plist"

DISPLAY_NAME="Trading Agents Lab"

if [[ ! -f "$PLIST" ]]; then
  # Not an error — `npm install` runs this BEFORE electron's own postinstall
  # downloads the binary. We'll be re-run later. Stay quiet so install logs
  # don't surface noisy false positives.
  echo "(electron not yet downloaded — skipping plist patch)"
  exit 0
fi

if [[ "$(uname)" != "Darwin" ]]; then
  # PlistBuddy + .app bundles are macOS-specific.
  exit 0
fi

CURRENT="$(/usr/libexec/PlistBuddy -c "Print :CFBundleName" "$PLIST" 2>/dev/null || echo "")"
if [[ "$CURRENT" == "$DISPLAY_NAME" ]]; then
  echo "Electron plist already patched ($DISPLAY_NAME)"
  exit 0
fi

/usr/libexec/PlistBuddy -c "Set :CFBundleName '$DISPLAY_NAME'" "$PLIST"
# CFBundleDisplayName may or may not exist depending on Electron version;
# `Add` errors out if it's already set, so we Set-then-Add as fallback.
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName '$DISPLAY_NAME'" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string '$DISPLAY_NAME'" "$PLIST"

# Touch the .app so Launch Services picks up the new metadata on the next
# launch. Without this, the dock can keep showing the cached "Electron"
# name until you restart the Mac.
touch "$ELECTRON_APP"

echo "Patched Electron Info.plist → $DISPLAY_NAME"
