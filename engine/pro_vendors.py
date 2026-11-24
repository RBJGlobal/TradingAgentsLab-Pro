"""Per-run data-vendor choices for the Pro graph (Full analysis).

Why this module exists
----------------------
The upstream graph's data tools (``get_news``, ``get_fundamentals``, ...) all
dispatch through ``tradingagents.dataflows.interface.route_to_vendor``, which
reads ``tool_vendors`` (per tool) before ``data_vendors`` (per category) from
the library config. The vendored default sends every category to yfinance, so
without an explicit choice an Alpha Vantage key would sit unused even though
the library ships complete Alpha Vantage implementations for these tools.

This module turns the user's two Settings choices into a ``tool_vendors``
mapping:

* **News source** (``news_source``): ``auto`` / ``alpaca`` / ``yfinance`` /
  ``alpha_vantage``. Drives ``get_news`` (news and social analysts) and, for
  Alpha Vantage, ``get_global_news`` too.
* **Fundamentals source** (``fundamentals_source``): ``yfinance`` (default) or
  ``alpha_vantage``. Drives the company overview, the three financial
  statements and insider transactions (no shipped analyst calls the insider
  tool today; it follows this choice so a future one stays consistent).

Rules
-----
* Alpha Vantage is opt-in. It is used only when the user picked it AND a key is
  present for this run. Without a key the choice degrades to Yahoo, so a stale
  preference can never break a run.
* Yahoo is always the tail of every chain. ``route_to_vendor`` moves to the
  next vendor when one raises a ``VendorError`` (rate limit, missing key, no
  data), so hitting the Alpha Vantage free tier's daily cap mid-run falls back
  to Yahoo instead of failing the run.
* Prices and technical indicators stay on Yahoo: the market analyst is not
  part of this choice (Alpha Vantage's adjusted daily series is premium-only).
"""
from __future__ import annotations

import functools
import json

from tradingagents.dataflows import interface
from tradingagents.dataflows.errors import NoMarketDataError

from . import alpaca_news

NEWS_SOURCES = ("auto", "alpaca", "yfinance", "alpha_vantage")
FUNDAMENTALS_SOURCES = ("yfinance", "alpha_vantage")

# Tools that follow the Fundamentals source choice.
FUNDAMENTALS_TOOLS = (
    "get_fundamentals",
    "get_balance_sheet",
    "get_cashflow",
    "get_income_statement",
    "get_insider_transactions",
)

_AV_THEN_YAHOO = "alpha_vantage,yfinance"


def _norm(value: object, allowed: tuple[str, ...], default: str) -> str:
    choice = str(value or default).strip().lower()
    return choice if choice in allowed else default


def pro_tool_vendors(
    news_source: object,
    fundamentals_source: object,
    *,
    alpaca_ready: bool,
    av_ready: bool,
) -> dict[str, str]:
    """Return the ``tool_vendors`` entries for one Pro run.

    ``alpaca_ready``: Alpaca is the connected data provider with both keys.
    ``av_ready``: an Alpha Vantage key was sent for this run.
    """
    news = _norm(news_source, NEWS_SOURCES, "auto")
    fundamentals = _norm(fundamentals_source, FUNDAMENTALS_SOURCES, "yfinance")

    # Every managed tool gets an explicit entry on EVERY run. The library's
    # set_config merges tool_vendors into a process-wide config rather than
    # replacing it, so an entry left out here would keep the previous run's
    # choice (an Alpha Vantage pick would outlive switching back to Yahoo).
    out: dict[str, str] = {}
    if news == "alpha_vantage":
        chain = _AV_THEN_YAHOO if av_ready else "yfinance"
        out["get_news"] = chain
        out["get_global_news"] = chain
    else:
        out["get_news"] = alpaca_news.news_vendor_chain(news, alpaca_ready)
        out["get_global_news"] = "yfinance"

    fund_chain = _AV_THEN_YAHOO if (fundamentals == "alpha_vantage" and av_ready) else "yfinance"
    for tool in FUNDAMENTALS_TOOLS:
        out[tool] = fund_chain
    return out


# ---- empty / error responses -------------------------------------------------
#
# Alpha Vantage answers some requests with HTTP 200 and a body that carries no
# data: "{}" for an ETF or unknown symbol on OVERVIEW, {"Error Message": ...}
# for a bad symbol, an empty news feed, or statements with no reports. The
# upstream implementations return those bodies as-is, so the router would hand
# them to the analyst as if they were data. The guard below raises
# NoMarketDataError instead, which makes route_to_vendor try Yahoo next.

GUARDED_TOOLS = ("get_news", "get_global_news") + FUNDAMENTALS_TOOLS


def _is_empty_av_body(result: object) -> bool:
    if isinstance(result, dict):
        body = result
    elif isinstance(result, str):
        text = result.strip()
        if not text.startswith("{"):
            return False  # CSV or prose: real data
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            return False
    else:
        return False
    if not isinstance(body, dict) or not body:
        return True
    if "Error Message" in body:
        return True
    if "feed" in body and not body.get("feed"):
        return True
    report_keys = [k for k in ("annualReports", "quarterlyReports") if k in body]
    if report_keys and not any(body.get(k) for k in report_keys):
        return True
    if "data" in body and set(body) <= {"symbol", "data"} and not body.get("data"):
        return True
    return False


def _guard(impl):
    if getattr(impl, "_tal_av_guard", False):
        return impl

    @functools.wraps(impl)
    def guarded(*args, **kwargs):
        result = impl(*args, **kwargs)
        if _is_empty_av_body(result):
            label = str(args[0]) if args else "request"
            raise NoMarketDataError(label, detail="Alpha Vantage returned no data")
        return result

    guarded._tal_av_guard = True  # type: ignore[attr-defined]
    return guarded


def register_alpha_vantage_guards() -> None:
    """Wrap the upstream alpha_vantage impls in the live dispatch table.
    Idempotent; does NOT edit the vendored ``tradingagents`` tree."""
    for tool in GUARDED_TOOLS:
        vendors = interface.VENDOR_METHODS.get(tool, {})
        if "alpha_vantage" in vendors:
            vendors["alpha_vantage"] = _guard(vendors["alpha_vantage"])
