"""Pro data-vendor choices (engine/pro_vendors.py): the News and Fundamentals
source settings map to per-tool vendor chains, Alpha Vantage only when picked
AND a key is present, Yahoo always the fallback.

No real network: dispatch tests swap the vendor implementations for fakes.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.alpha_vantage_common import (
    AlphaVantageNotConfiguredError,
    AlphaVantageRateLimitError,
)
from tradingagents.dataflows.config import get_config, set_config

from engine.pro_vendors import (
    FUNDAMENTALS_TOOLS,
    _is_empty_av_body,
    pro_tool_vendors,
    register_alpha_vantage_guards,
)


@pytest.fixture
def _restore_config():
    original = deepcopy(get_config())
    try:
        yield
    finally:
        set_config(original)


# ---- mapping ---------------------------------------------------------------

YAHOO_FUND = {t: "yfinance" for t in FUNDAMENTALS_TOOLS}
AV_FUND = {t: "alpha_vantage,yfinance" for t in FUNDAMENTALS_TOOLS}


def _expect(news, global_news="yfinance", fund=None):
    return {"get_news": news, "get_global_news": global_news, **(fund or YAHOO_FUND)}


def test_defaults_keep_every_tool_on_free_sources():
    out = pro_tool_vendors(None, None, alpaca_ready=False, av_ready=True)
    assert out == _expect("yfinance")


def test_existing_news_choices_unchanged():
    assert pro_tool_vendors("auto", None, alpaca_ready=True, av_ready=False) == _expect(
        "alpaca,yfinance"
    )
    assert pro_tool_vendors("alpaca", None, alpaca_ready=False, av_ready=False) == _expect(
        "alpaca,yfinance"
    )
    assert pro_tool_vendors("yfinance", None, alpaca_ready=True, av_ready=True) == _expect(
        "yfinance"
    )


def test_news_alpha_vantage_with_key():
    out = pro_tool_vendors("alpha_vantage", "yfinance", alpaca_ready=True, av_ready=True)
    assert out == _expect("alpha_vantage,yfinance", "alpha_vantage,yfinance")


def test_news_alpha_vantage_without_key_degrades_to_yahoo():
    out = pro_tool_vendors("alpha_vantage", None, alpaca_ready=True, av_ready=False)
    assert out == _expect("yfinance")


def test_fundamentals_alpha_vantage_with_key():
    out = pro_tool_vendors("auto", "alpha_vantage", alpaca_ready=False, av_ready=True)
    assert out == _expect("yfinance", fund=AV_FUND)


def test_fundamentals_alpha_vantage_without_key_stays_default():
    out = pro_tool_vendors("auto", "alpha_vantage", alpaca_ready=False, av_ready=False)
    assert out == _expect("yfinance")


@pytest.mark.parametrize("bad", ["bloomberg", "", 42, "  ALPHA_VANTAGE  "])
def test_unknown_or_messy_values(bad):
    out = pro_tool_vendors(bad, bad, alpaca_ready=False, av_ready=True)
    if bad == "  ALPHA_VANTAGE  ":
        # Normalized, not rejected.
        assert out == _expect("alpha_vantage,yfinance", "alpha_vantage,yfinance", AV_FUND)
    else:
        assert out == _expect("yfinance")


def _merge_like_server(choices):
    """What server.py does each run: merge into tool_vendors, then the graph
    calls set_config (which merges one level deep into the global config)."""
    cfg = deepcopy(get_config())
    tv = dict(cfg.get("tool_vendors") or {})
    tv.update(choices)
    set_config({"tool_vendors": tv})


def test_switching_back_to_yahoo_does_not_keep_alpha_vantage(_restore_config):
    """Regression: set_config merges into a process-wide config, so a run that
    picked Alpha Vantage must not leak its chains into the next run."""
    _merge_like_server(
        pro_tool_vendors("alpha_vantage", "alpha_vantage", alpaca_ready=False, av_ready=True)
    )
    assert interface.get_vendor("fundamental_data", "get_fundamentals") == "alpha_vantage,yfinance"
    _merge_like_server(pro_tool_vendors("auto", "yfinance", alpaca_ready=False, av_ready=True))
    for tool in ("get_news", "get_global_news") + FUNDAMENTALS_TOOLS:
        category = interface.get_category_for_method(tool)
        assert "alpha_vantage" not in interface.get_vendor(category, tool), tool


def test_every_chosen_tool_has_both_vendors_upstream():
    """Guard against an upstream refresh renaming a tool or dropping a vendor:
    route_to_vendor raises on a configured vendor it does not know."""
    out = pro_tool_vendors("alpha_vantage", "alpha_vantage", alpaca_ready=False, av_ready=True)
    for tool, chain in out.items():
        for vendor in chain.split(","):
            assert vendor in interface.VENDOR_METHODS[tool], (tool, vendor)


# ---- dispatch through the real router --------------------------------------


def _apply(choices):
    cfg = deepcopy(get_config())
    cfg["tool_vendors"] = dict(choices)
    set_config(cfg)


def test_dispatch_uses_alpha_vantage_first(monkeypatch, _restore_config):
    monkeypatch.setitem(
        interface.VENDOR_METHODS["get_fundamentals"], "alpha_vantage", lambda *a, **k: "AV"
    )

    def yahoo(*a, **k):  # pragma: no cover - must NOT run
        raise AssertionError("Yahoo should not run when Alpha Vantage answers")

    monkeypatch.setitem(interface.VENDOR_METHODS["get_fundamentals"], "yfinance", yahoo)
    _apply(pro_tool_vendors("auto", "alpha_vantage", alpaca_ready=False, av_ready=True))
    assert interface.route_to_vendor("get_fundamentals", "NVDA", "2026-11-20") == "AV"


@pytest.mark.parametrize(
    "error",
    [
        AlphaVantageRateLimitError("Alpha Vantage rate limit exceeded: 25 requests per day"),
        AlphaVantageNotConfiguredError("Alpha Vantage API key invalid or missing"),
    ],
)
def test_dispatch_falls_back_to_yahoo(monkeypatch, _restore_config, error):
    def av(*a, **k):
        raise error

    monkeypatch.setitem(interface.VENDOR_METHODS["get_news"], "alpha_vantage", av)
    monkeypatch.setitem(interface.VENDOR_METHODS["get_news"], "yfinance", lambda *a, **k: "YAHOO")
    _apply(pro_tool_vendors("alpha_vantage", None, alpaca_ready=False, av_ready=True))
    assert interface.route_to_vendor("get_news", "NVDA", "2026-11-01", "2026-11-20") == "YAHOO"


# ---- empty / error body guard -----------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "{}",
        {},
        '{"Error Message": "Invalid API call."}',
        '{"items": "0", "feed": []}',
        '{"symbol": "SPY", "annualReports": [], "quarterlyReports": []}',
        '{"symbol": "X", "data": []}',
    ],
)
def test_empty_bodies_detected(body):
    assert _is_empty_av_body(body)


@pytest.mark.parametrize(
    "body",
    [
        '{"Symbol": "IBM", "Name": "International Business Machines"}',
        '{"items": "2", "feed": [{"title": "a"}]}',
        '{"symbol": "IBM", "annualReports": [{"fiscalDateEnding": "2025-12-31"}]}',
        "timestamp,open,high\n2026-11-20,1,2",
        "## IBM News",
    ],
)
def test_real_bodies_pass(body):
    assert not _is_empty_av_body(body)


def test_guard_makes_empty_av_body_fall_back(monkeypatch, _restore_config):
    monkeypatch.setitem(
        interface.VENDOR_METHODS["get_fundamentals"], "alpha_vantage", lambda *a, **k: "{}"
    )
    monkeypatch.setitem(
        interface.VENDOR_METHODS["get_fundamentals"], "yfinance", lambda *a, **k: "YAHOO"
    )
    register_alpha_vantage_guards()
    register_alpha_vantage_guards()  # idempotent: no double wrap
    impl = interface.VENDOR_METHODS["get_fundamentals"]["alpha_vantage"]
    assert getattr(impl, "_tal_av_guard", False)
    assert not getattr(getattr(impl, "__wrapped__", None), "_tal_av_guard", False)
    _apply(pro_tool_vendors("auto", "alpha_vantage", alpaca_ready=False, av_ready=True))
    assert interface.route_to_vendor("get_fundamentals", "SPY", "2026-11-20") == "YAHOO"
