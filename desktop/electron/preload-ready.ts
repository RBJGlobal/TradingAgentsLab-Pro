import { existsSync } from 'node:fs';

/**
 * Wait until the preload bundle exists on disk, up to `timeoutMs`.
 *
 * Why this exists: in dev, `vite-plugin-electron` can spawn Electron before it
 * finishes writing the preload bundle on a cold first boot. If `createWindow()`
 * calls `loadURL()` before the preload file is on disk, the window loads with
 * no `contextBridge` — `window.tradingAgentsLab` is undefined — and stays
 * broken for the life of the process: a manual reload just re-runs the same
 * already-loaded page (the failure is cached on the webContents). The founder
 * hit exactly this on the first `npm run dev` of a session (Settings threw
 * "secrets bridge not available — preload not loaded"); every relaunch worked
 * because the preload file already existed by then. Blocking the first load
 * until the preload is present closes that race.
 *
 * Rollup writes the bundle atomically (temp file + rename), so existence
 * implies a complete file — no partial-read window.
 *
 * Bounded by `timeoutMs` so a genuine build failure can't hang the window
 * forever: after the timeout we proceed and let the normal "bridge not
 * available" error surface rather than blocking startup indefinitely.
 *
 * No-op in practice on warm relaunches (the file already exists) and in
 * production (the preload is bundled into the .app, always present, and main
 * loads via `loadFile` not `loadURL`).
 *
 * @returns `true` if the preload is present, `false` if it gave up at timeout.
 */
export async function waitForPreload(
  preloadPath: string,
  timeoutMs = 5000,
  pollMs = 50,
): Promise<boolean> {
  const deadline = Date.now() + timeoutMs;
  while (!existsSync(preloadPath)) {
    if (Date.now() >= deadline) return false;
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
  return true;
}
