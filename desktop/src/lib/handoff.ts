/**
 * Cross-page handoff helpers.
 *
 * The Watchlist's "Analyze" button hands a ticker off to the Analyze page
 * via sessionStorage. The Analyze page reads it on mount and clears the
 * key. Both sides import the same constant from here so the key never
 * drifts.
 *
 * sessionStorage (not localStorage) so the handoff is window-scoped — a
 * second BrowserWindow won't accidentally pick up the value.
 */

export const PENDING_TICKER_KEY = 'tal:pending-analyze-ticker';

export function setPendingTicker(ticker: string): void {
  try {
    sessionStorage.setItem(PENDING_TICKER_KEY, ticker.toUpperCase());
  } catch {
    // sessionStorage can fail (private mode, quota). Caller falls through
    // to the default ticker.
  }
}

export function consumePendingTicker(): string | null {
  try {
    const value = sessionStorage.getItem(PENDING_TICKER_KEY);
    if (value) {
      sessionStorage.removeItem(PENDING_TICKER_KEY);
      return value.toUpperCase();
    }
  } catch {
    // Ignore — caller falls through.
  }
  return null;
}
