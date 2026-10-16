"""Alpaca (Benzinga) news as an upstream ``get_news`` vendor.

Why this module exists
----------------------
The Pro graph's news analyst calls the upstream ``get_news(ticker, start, end)``
tool, which dispatches through ``tradingagents.dataflows.interface.route_to_vendor``
on the configured ``news_data`` vendor. Upstream ships only ``yfinance`` and
``alpha_vantage``. yfinance's Yahoo news endpoint has degraded and returns empty
for many liquid equities (observed live: TEM returned zero news on 2026-10-15
while four Benzinga stories existed for the same window), so the analyst reasons
as if there is no news. Meanwhile Alpaca's Benzinga feed, which already powers the
chrome "News headlines" card (``data_providers._alpaca_news``), is reliable.

This module registers an ``alpaca`` vendor for ``get_news`` so an Alpaca-connected
user's news analyst reads the same Benzinga stories the UI already shows.

Design notes
------------
* The vendored ``tradingagents/`` tree is NOT edited. We register into the live
  dispatch table at runtime (``register_alpaca_news_vendor``) and select it by
  setting ``tool_vendors["get_news"] = "alpaca,yfinance"`` in the Pro library
  config (done in ``server.py`` when Alpaca is the connected data provider).
* The ``,yfinance`` tail is the fallback. ``route_to_vendor`` advances to the next
  vendor whenever this impl raises a ``VendorError`` (Alpaca down, misconfigured,
  or empty for the window), so a single empty source never blanks the analyst.
* This impl is synchronous because the upstream tool contract is synchronous
  (``route_to_vendor`` calls ``impl(*args)`` directly, like ``get_news_yfinance``).
  It therefore uses a sync ``httpx.Client`` rather than the async
  ``AlpacaProvider``, and reads credentials from the environment, mirroring the
  per-run env injection ``full_debate`` already uses for ``ALPHA_VANTAGE_API_KEY``.
  Runs are processed one at a time per engine process, same as that pattern.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

import httpx

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
)
from tradingagents.dataflows import interface

# Data-only endpoint. Mirrors data_providers.ALPACA_DATA_BASE_URL — this must
# NEVER resolve to api.alpaca.markets (locked positioning: the engine connects
# only to data/paper endpoints, enforced by the constant, not a runtime flag).
ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"

# Env vars carrying the run's Alpaca data keys (Alpaca's own conventional names).
_KEY_ID_ENV = "APCA_API_KEY_ID"
_SECRET_ENV = "APCA_API_SECRET_KEY"

_DEFAULT_ARTICLE_LIMIT = 20
_MAX_ARTICLE_LIMIT = 50


def set_alpaca_news_credentials(key_id: str | None, secret: str | None) -> None:
    """Expose the run's Alpaca data keys to the sync news vendor via env.

    Mirrors ``full_debate``'s handling of ``ALPHA_VANTAGE_API_KEY``: set when
    present, clear when absent so a later non-Alpaca run can never reuse stale
    keys from an earlier one.
    """
    if key_id and secret:
        os.environ[_KEY_ID_ENV] = key_id
        os.environ[_SECRET_ENV] = secret
    else:
        os.environ.pop(_KEY_ID_ENV, None)
        os.environ.pop(_SECRET_ENV, None)


def format_alpaca_news(
    ticker: str, start_date: str, end_date: str, items: list
) -> str:
    """Render Alpaca news items into the exact string shape ``get_news_yfinance``
    returns, so the analyst sees a consistent report regardless of which vendor
    served it.

    Raises ``NoMarketDataError`` when nothing usable is in the window. That is
    the signal ``route_to_vendor`` needs to fall through to the yfinance
    fallback: a plain empty string would be treated as a successful answer and
    would stop the chain.
    """
    blocks: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = (item.get("headline") or "").strip()
        if not title:
            continue
        publisher = (item.get("source") or item.get("author") or "").strip() or "Alpaca"
        summary = (item.get("summary") or "").strip()
        url = (item.get("url") or "").strip()
        block = f"### {title} (source: {publisher})\n"
        if summary:
            block += f"{summary}\n"
        if url:
            block += f"Link: {url}\n"
        blocks.append(block)

    if not blocks:
        raise NoMarketDataError(
            ticker,
            detail=f"Alpaca returned no news between {start_date} and {end_date}",
        )

    body = "\n".join(blocks) + "\n"
    return f"## {ticker} News, from {start_date} to {end_date}:\n\n{body}"


def alpaca_get_news(ticker: str, start_date: str, end_date: str) -> str:
    """``get_news`` vendor implementation backed by Alpaca's Benzinga feed.

    Returns the formatted news report on success. Raises a ``VendorError`` on
    any failure (missing creds, network/HTTP error, or no articles in the
    window) so ``route_to_vendor`` advances to the configured fallback vendor.
    """
    key_id = os.environ.get(_KEY_ID_ENV)
    secret = os.environ.get(_SECRET_ENV)
    if not (key_id and secret):
        # Selected without creds in env -> treat as unavailable so the router
        # moves to the yfinance fallback instead of raising out of the tool.
        raise VendorNotConfiguredError(
            f"Alpaca news selected for {ticker} but credentials are not set"
        )

    # Canonicalize once so the query symbol and the report header agree.
    symbol = ticker.strip().upper()

    try:
        limit = int(get_config().get("news_article_limit", _DEFAULT_ARTICLE_LIMIT))
    except Exception:
        limit = _DEFAULT_ARTICLE_LIMIT
    limit = max(1, min(limit, _MAX_ARTICLE_LIMIT))

    params = {
        "symbols": symbol,
        "limit": str(limit),
        "include_content": "false",
        "sort": "desc",
        # Bound the window server-side. The end bound keeps the tool look-ahead
        # safe: a backtest/as-of date never pulls news published after it.
        "start": f"{start_date}T00:00:00Z",
        "end": f"{end_date}T23:59:59Z",
    }
    headers = {
        "APCA-API-KEY-ID": key_id,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    }
    url = f"{ALPACA_DATA_BASE_URL}/v1beta1/news"

    t0 = datetime.now(timezone.utc)
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params, headers=headers)
    except Exception as exc:  # noqa: BLE001 — surface as a fall-through signal
        sys.stderr.write(
            f"[alpaca-news] FAILED {ticker} ({type(exc).__name__}: {exc})\n"
        )
        raise NoMarketDataError(
            ticker, detail=f"Alpaca news request failed: {type(exc).__name__}"
        ) from exc

    if resp.status_code != 200:
        sys.stderr.write(
            f"[alpaca-news] NON-200 {ticker} status={resp.status_code} "
            f"body={resp.text[:120]!r}\n"
        )
        # 401/403 are a configuration problem; everything else is "no data here".
        if resp.status_code in (401, 403):
            raise VendorNotConfiguredError(
                f"Alpaca rejected credentials for news ({resp.status_code})"
            )
        raise NoMarketDataError(
            ticker, detail=f"Alpaca news HTTP {resp.status_code}"
        )

    body = resp.json() or {}
    items = body.get("news") or []
    report = format_alpaca_news(symbol, start_date, end_date, items)  # raises on empty
    elapsed_ms = int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
    sys.stderr.write(
        f"[alpaca-news] OK {symbol} -> {len(items)} items in {elapsed_ms}ms\n"
    )
    return report


def register_alpaca_news_vendor() -> None:
    """Register the Alpaca news impl into the upstream ``get_news`` dispatch
    table. Idempotent; does NOT edit the vendored ``tradingagents`` tree."""
    interface.VENDOR_METHODS.setdefault("get_news", {})["alpaca"] = alpaca_get_news
