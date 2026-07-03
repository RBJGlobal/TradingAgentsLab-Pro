import { BrowserWindow } from 'electron';

/**
 * In-app Alpha Vantage free-key signup (defensive against funnelling our paying
 * users to the competitor promo Alpha Vantage shows below the issued key).
 *
 * We open Alpha Vantage's REAL key page in a fully isolated child window. The
 * user fills the real form themselves (no automation, no page modification), we
 * watch for the issued key, and the moment it appears we hand it back and close
 * the window BEFORE the user can scroll to the promo shown beneath it. If the
 * page ever changes and capture misses, the window simply stays open and the
 * user copies the key manually into Settings, so the flow degrades gracefully
 * rather than breaking.
 */

const AV_KEY_URL = 'https://www.alphavantage.co/support/#api-key';

// Alpha Vantage's confirmed result message: "Welcome to Alpha Vantage! Here is
// your API key: XXXXXXXXXXXXXXXX. Please record this API key at a safe place..."
// followed a few lines down by a competitor promo. We anchor on "API key:"
// then the token (16 uppercase-alphanumeric chars; range allows for drift).
// That labelled-token pattern does not exist before the form is submitted, so
// there are no false positives from the form/docs, and matching text (not exact
// HTML) survives minor markup changes.
const KEY_IN_RESULT = /API key:\s*([A-Z0-9]{12,24})/i;

// Poll fast so we capture-and-close within a few hundred ms of the key
// appearing, before the user can read down to the promo shown beneath it.
const POLL_MS = 350;

/**
 * Resolves with the captured key, or null if the user closed the window first.
 */
export function openAlphaVantageSignup(
  parent: BrowserWindow | null,
): Promise<string | null> {
  return new Promise((resolve) => {
    const child = new BrowserWindow({
      parent: parent ?? undefined,
      modal: false,
      width: 760,
      height: 800,
      title: 'Get a free Alpha Vantage key',
      backgroundColor: '#0d1117',
      autoHideMenuBar: true,
      webPreferences: {
        // Hard isolation: the external page runs walled off and cannot reach
        // any of our app internals. No preload is injected into it.
        nodeIntegration: false,
        contextIsolation: true,
        sandbox: true,
      },
    });

    // Keep the flow contained: deny any popups the external page tries to open.
    child.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));

    let settled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const finish = (key: string | null) => {
      if (settled) return;
      settled = true;
      if (timer) clearInterval(timer);
      if (!child.isDestroyed()) child.close();
      resolve(key);
    };

    void child.loadURL(AV_KEY_URL);

    // Poll the page text for the issued key. Reading via executeJavaScript from
    // the main process keeps the external page passive (read-only, no injected
    // bridge). We only ever read innerText, never write.
    timer = setInterval(() => {
      if (child.isDestroyed()) {
        finish(null);
        return;
      }
      child.webContents
        .executeJavaScript(
          'document.documentElement ? document.documentElement.innerText : ""',
        )
        .then((text: unknown) => {
          if (typeof text === 'string') {
            const m = text.match(KEY_IN_RESULT);
            if (m && m[1]) finish(m[1]);
          }
        })
        .catch(() => {
          /* page navigating / not ready yet — keep polling */
        });
    }, POLL_MS);

    child.on('closed', () => finish(null));
  });
}
