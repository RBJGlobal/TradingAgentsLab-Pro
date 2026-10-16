"""Alpaca news vendor (engine/alpaca_news.py) — formatting, failure modes,
and the upstream dispatch wiring that gives "Alpaca first, Yahoo fallback".

No real network: the sync httpx.Client is swapped for an httpx.MockTransport,
mirroring test_alpaca_provider.py (which does the same for the async client).
"""

from __future__ import annotations

from copy import deepcopy

import httpx
import pytest

from tradingagents.dataflows import interface
from tradingagents.dataflows.config import get_config, set_config
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
)

from engine import alpaca_news


# ---- helpers ---------------------------------------------------------------


def _use_mock_client(handler):
    """Return a context-managed swap of httpx.Client for a MockTransport one."""
    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    return real_client, patched_client


_BENZINGA_ITEM = {
    "headline": "Tempus AI Doubles Down On Moderna and Merck",
    "summary": "Expanded collaboration on cancer vaccine infrastructure.",
    "url": "https://www.benzinga.com/news/tem-moderna",
    "source": "benzinga",
    "created_at": "2026-10-07T17:44:52Z",
}


# ---- pure formatting -------------------------------------------------------


def test_format_matches_yfinance_report_shape():
    out = alpaca_news.format_alpaca_news("TEM", "2026-10-01", "2026-10-15", [_BENZINGA_ITEM])
    assert out.startswith("## TEM News, from 2026-10-01 to 2026-10-15:")
    assert "### Tempus AI Doubles Down On Moderna and Merck (source: benzinga)" in out
    assert "Expanded collaboration on cancer vaccine infrastructure." in out
    assert "Link: https://www.benzinga.com/news/tem-moderna" in out


def test_format_skips_items_without_a_headline():
    items = [{"summary": "no title here"}, _BENZINGA_ITEM]
    out = alpaca_news.format_alpaca_news("TEM", "2026-10-01", "2026-10-15", items)
    # Only the real headline survives.
    assert out.count("### ") == 1


def test_format_raises_no_market_data_on_empty():
    with pytest.raises(NoMarketDataError):
        alpaca_news.format_alpaca_news("TEM", "2026-10-01", "2026-10-15", [])
    # Items present but all unusable (no headline) also counts as no data.
    with pytest.raises(NoMarketDataError):
        alpaca_news.format_alpaca_news("TEM", "2026-10-01", "2026-10-15", [{"summary": "x"}])


# ---- alpaca_get_news: HTTP shape + success ---------------------------------


def test_get_news_builds_request_and_returns_report(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "PK_TEST")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "secret_test")

    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"news": [_BENZINGA_ITEM]})

    real_client, patched = _use_mock_client(handler)
    monkeypatch.setattr(httpx, "Client", patched)

    out = alpaca_news.alpaca_get_news("tem", "2026-10-01", "2026-10-15")

    assert len(captured) == 1
    req = captured[0]
    assert str(req.url).startswith("https://data.alpaca.markets/v1beta1/news")
    qp = dict(req.url.params)
    assert qp["symbols"] == "TEM"  # upcased
    assert qp["start"] == "2026-10-01T00:00:00Z"
    assert qp["end"] == "2026-10-15T23:59:59Z"  # look-ahead safe upper bound
    assert req.headers["APCA-API-KEY-ID"] == "PK_TEST"
    assert req.headers["APCA-API-SECRET-KEY"] == "secret_test"
    assert out.startswith("## TEM News,")
    assert "Moderna and Merck" in out


# ---- alpaca_get_news: failure modes raise VendorError (-> router fallback) --


def test_get_news_raises_when_creds_absent(monkeypatch):
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    monkeypatch.delenv("APCA_API_SECRET_KEY", raising=False)
    with pytest.raises(VendorNotConfiguredError):
        alpaca_news.alpaca_get_news("TEM", "2026-10-01", "2026-10-15")


def test_get_news_raises_not_configured_on_401(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "bad")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "bad")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="invalid credentials")

    real_client, patched = _use_mock_client(handler)
    monkeypatch.setattr(httpx, "Client", patched)

    with pytest.raises(VendorNotConfiguredError):
        alpaca_news.alpaca_get_news("TEM", "2026-10-01", "2026-10-15")


def test_get_news_raises_no_data_on_empty_window(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "PK_TEST")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "secret_test")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"news": []})

    real_client, patched = _use_mock_client(handler)
    monkeypatch.setattr(httpx, "Client", patched)

    with pytest.raises(NoMarketDataError):
        alpaca_news.alpaca_get_news("TEM", "2026-10-01", "2026-10-15")


def test_get_news_raises_no_data_on_5xx(monkeypatch):
    monkeypatch.setenv("APCA_API_KEY_ID", "PK_TEST")
    monkeypatch.setenv("APCA_API_SECRET_KEY", "secret_test")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    real_client, patched = _use_mock_client(handler)
    monkeypatch.setattr(httpx, "Client", patched)

    with pytest.raises(NoMarketDataError):
        alpaca_news.alpaca_get_news("TEM", "2026-10-01", "2026-10-15")


# ---- the real win: register + dispatch = Alpaca first, Yahoo fallback ------


@pytest.fixture
def _restore_config():
    """Snapshot/restore the dataflows global config so vendor-selection tests
    don't leak into the rest of the suite."""
    original = deepcopy(get_config())
    try:
        yield
    finally:
        set_config(original)


def test_dispatch_prefers_alpaca_when_it_has_news(monkeypatch, _restore_config):
    alpaca_news.register_alpaca_news_vendor()

    def fake_alpaca(ticker, start, end):
        return "## ALPACA REPORT ##"

    def fake_yfinance(ticker, start, end):  # pragma: no cover - must NOT run
        raise AssertionError("yfinance should not be called when Alpaca has news")

    monkeypatch.setitem(interface.VENDOR_METHODS["get_news"], "alpaca", fake_alpaca)
    monkeypatch.setitem(interface.VENDOR_METHODS["get_news"], "yfinance", fake_yfinance)

    cfg = deepcopy(get_config())
    cfg["tool_vendors"] = {"get_news": "alpaca,yfinance"}
    set_config(cfg)

    out = interface.route_to_vendor("get_news", "TEM", "2026-10-01", "2026-10-15")
    assert out == "## ALPACA REPORT ##"


def test_dispatch_falls_back_to_yfinance_when_alpaca_empty(monkeypatch, _restore_config):
    alpaca_news.register_alpaca_news_vendor()

    def fake_alpaca(ticker, start, end):
        raise NoMarketDataError(ticker, detail="alpaca empty")

    def fake_yfinance(ticker, start, end):
        return "## YFINANCE FALLBACK REPORT ##"

    monkeypatch.setitem(interface.VENDOR_METHODS["get_news"], "alpaca", fake_alpaca)
    monkeypatch.setitem(interface.VENDOR_METHODS["get_news"], "yfinance", fake_yfinance)

    cfg = deepcopy(get_config())
    cfg["tool_vendors"] = {"get_news": "alpaca,yfinance"}
    set_config(cfg)

    out = interface.route_to_vendor("get_news", "TEM", "2026-10-01", "2026-10-15")
    assert out == "## YFINANCE FALLBACK REPORT ##"
