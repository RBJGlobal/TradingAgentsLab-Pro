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
  statements and insider transactions.

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

    out: dict[str, str] = {}
    if news == "alpha_vantage":
        chain = _AV_THEN_YAHOO if av_ready else "yfinance"
        out["get_news"] = chain
        out["get_global_news"] = chain
    else:
        out["get_news"] = alpaca_news.news_vendor_chain(news, alpaca_ready)

    if fundamentals == "alpha_vantage" and av_ready:
        for tool in FUNDAMENTALS_TOOLS:
            out[tool] = _AV_THEN_YAHOO
    return out
