---
order: 130
---

# Keyboard Shortcuts

*Every keyboard shortcut in Trading Agents Lab Pro: menu accelerators and page-level shortcuts.*

> **For educational research and paper trading. This is not investment advice.**

---

## Menu bar shortcuts

These are defined in the app's menu and are active from anywhere in the app.

### App menu (Trading Agents Lab Pro, macOS)

| Shortcut | Action |
|---|---|
| `Cmd+,` | Open Settings |

### File menu

| Shortcut | Action |
|---|---|
| `Cmd+N` | New analysis: goes to the Analyze page, ends any analysis in progress, and clears the previous results |
| `Cmd+.` | Stop streaming: closes the connection to the engine if an analysis is in progress |

### Go menu

| Shortcut | Action |
|---|---|
| `Cmd+1` | Go to Analyze |
| `Cmd+2` | Go to Watchlist |
| `Cmd+3` | Go to History |
| `Cmd+,` | Go to Settings (same as the App menu on macOS) |

### Edit menu

Standard editing shortcuts, which are platform defaults:

| Shortcut | Action |
|---|---|
| `Cmd+Z` | Undo |
| `Cmd+Shift+Z` | Redo |
| `Cmd+X` | Cut |
| `Cmd+C` | Copy |
| `Cmd+V` | Paste |
| `Cmd+A` | Select all |

### View menu

| Shortcut | Action |
|---|---|
| `Cmd+R` | Reload the window |
| `Cmd+Shift+R` | Force reload (bypasses the cache) |
| `Cmd+Option+I` | Toggle Developer Tools |
| `Cmd+0` | Reset zoom |
| `Cmd++` | Zoom in |
| `Cmd+-` | Zoom out |
| `Ctrl+Cmd+F` | Toggle full screen |

### Window menu (macOS)

| Shortcut | Action |
|---|---|
| `Cmd+M` | Minimize |

---

## Page-level shortcuts

These are handled by the Analyze page.

| Shortcut | Action | Condition |
|---|---|---|
| `Cmd+Enter` | Run analysis with the ticker, date, mode and model currently selected | The engine is running and no analysis is currently streaming |
| `Cmd+.` | Stop streaming | Same as the File menu item; works at page level too |

On Windows and Linux, `Cmd` maps to `Ctrl` for all shortcuts above.

---

## Notes

- `Cmd+N` ends an analysis that is in progress as well as clearing the page. Whatever the run had already spent still counts toward your Cost Guard totals (see [cost-guard.md](cost-guard.md)).
- `Cmd+.` is safe to press when nothing is streaming. It does nothing.
- The Help menu has **Check for Updates…** (opens Settings, where the Updates tab manages updates), **Visit Trading Agents Lab** (opens the website in your browser), **Contact Support** (opens an email to the support address) and **Open Settings**.

---

## Further reading

- [Reading the debate](reading-the-debate.md), how to use the Analyze page
- [Getting started](getting-started.md), first-run setup
