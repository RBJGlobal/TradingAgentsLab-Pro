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

from engine.pro_vendors import FUNDAMENTALS_TOOLS, pro_tool_vendors


@pytest.fixture
def _restore_config():
    original = deepcopy(get_config())
    try:
        yield
    finally:
        set_config(original)


# ---- mapping ---------------------------------------------------------------


def test_defaults_keep_every_tool_on_free_sources():
    out = pro_tool_vendors(None, None, alpaca_ready=False, av_ready=True)
    assert out == {"get_news": "yfinance"}


def test_existing_news_choices_unchanged():
    assert pro_tool_vendors("auto", None, alpaca_ready=True, av_ready=False) == {
        "get_news": "alpaca,yfinance"
    }
    assert pro_tool_vendors("alpaca", None, alpaca_ready=False, av_ready=False) == {
        "get_news": "alpaca,yfinance"
    }
    assert pro_tool_vendors("yfinance", None, alpaca_ready=True, av_ready=True) == {
        "get_news": "yfinance"
    }


def test_news_alpha_vantage_with_key():
    out = pro_tool_vendors("alpha_vantage", "yfinance", alpaca_ready=True, av_ready=True)
    assert out["get_news"] == "alpha_vantage,yfinance"
    assert out["get_global_news"] == "alpha_vantage,yfinance"
    for tool in FUNDAMENTALS_TOOLS:
        assert tool not in out


def test_news_alpha_vantage_without_key_degrades_to_yahoo():
    out = pro_tool_vendors("alpha_vantage", None, alpaca_ready=True, av_ready=False)
    assert out == {"get_news": "yfinance", "get_global_news": "yfinance"}


def test_fundamentals_alpha_vantage_with_key():
    out = pro_tool_vendors("auto", "alpha_vantage", alpaca_ready=False, av_ready=True)
    assert out["get_news"] == "yfinance"
    for tool in FUNDAMENTALS_TOOLS:
        assert out[tool] == "alpha_vantage,yfinance"


def test_fundamentals_alpha_vantage_without_key_stays_default():
    out = pro_tool_vendors("auto", "alpha_vantage", alpaca_ready=False, av_ready=False)
    assert out == {"get_news": "yfinance"}


@pytest.mark.parametrize("bad", ["bloomberg", "", 42, "  ALPHA_VANTAGE  "])
def test_unknown_or_messy_values(bad):
    out = pro_tool_vendors(bad, bad, alpaca_ready=False, av_ready=True)
    if bad == "  ALPHA_VANTAGE  ":
        # Normalized, not rejected.
        assert out["get_news"] == "alpha_vantage,yfinance"
        assert out["get_fundamentals"] == "alpha_vantage,yfinance"
    else:
        assert out == {"get_news": "yfinance"}


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
