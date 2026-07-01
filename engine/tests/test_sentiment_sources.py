"""Tests for the social-sentiment fetchers (StockTwits + Reddit).

All network calls are stubbed via patching urllib.request.urlopen — we
don't want CI to depend on either endpoint being reachable, and the
fetchers' value is in their parsing + graceful-degradation logic, not
in proving the public endpoints exist.
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from engine import sentiment_sources


# ---- StockTwits ----------------------------------------------------------


def _mock_urlopen(body: dict | bytes):
    """Helper: build a context-manager mock that yields a response
    whose .read() returns the given body (encoded if it's a dict)."""
    encoded = json.dumps(body).encode() if isinstance(body, dict) else body
    response = MagicMock()
    response.read = MagicMock(return_value=encoded)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=response)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_stocktwits_parses_typical_payload():
    """Happy path: messages with mixed bull/bear/no-label labels produce
    a compact summary line + per-message lines."""
    body = {
        "messages": [
            {
                "created_at": "2026-05-13T10:00:00Z",
                "user": {"username": "alice"},
                "entities": {"sentiment": {"basic": "Bullish"}},
                "body": "long calls into earnings",
            },
            {
                "created_at": "2026-05-13T10:05:00Z",
                "user": {"username": "bob"},
                "entities": {"sentiment": {"basic": "Bearish"}},
                "body": "overvalued imo",
            },
            {
                "created_at": "2026-05-13T10:06:00Z",
                "user": {"username": "carol"},
                "entities": {"sentiment": None},
                "body": "anyone seen the chart?",
            },
        ]
    }
    with patch(
        "engine.sentiment_sources.urlopen",
        return_value=_mock_urlopen(body),
    ):
        result = sentiment_sources.fetch_stocktwits_messages("NVDA")

    assert "Bullish: 1 (33%)" in result
    assert "Bearish: 1 (33%)" in result
    assert "Unlabeled: 1" in result
    assert "Total: 3" in result
    assert "@alice" in result
    assert "@bob" in result
    assert "@carol" in result


def test_stocktwits_returns_placeholder_on_http_error():
    """502, 429, etc → return a placeholder string. The caller doesn't
    need to handle exceptions; it always gets a string."""
    err = HTTPError("u", 502, "bad gateway", {}, io.BytesIO(b""))
    with patch("engine.sentiment_sources.urlopen", side_effect=err):
        result = sentiment_sources.fetch_stocktwits_messages("NVDA")
    assert result.startswith("<stocktwits unavailable")
    assert "HTTPError" in result


def test_stocktwits_returns_placeholder_on_url_error():
    """DNS failure / connection refused → placeholder."""
    with patch(
        "engine.sentiment_sources.urlopen",
        side_effect=URLError("connection refused"),
    ):
        result = sentiment_sources.fetch_stocktwits_messages("NVDA")
    assert result.startswith("<stocktwits unavailable")


def test_stocktwits_handles_empty_messages():
    """Symbol with zero messages → clear placeholder, not a crash."""
    with patch(
        "engine.sentiment_sources.urlopen",
        return_value=_mock_urlopen({"messages": []}),
    ):
        result = sentiment_sources.fetch_stocktwits_messages("ZZZZ")
    assert "no StockTwits messages found" in result
    assert "$ZZZZ" in result


def test_stocktwits_handles_malformed_shape():
    """Garbage body → placeholder, not a stacktrace."""
    with patch(
        "engine.sentiment_sources.urlopen",
        return_value=_mock_urlopen({"unexpected": True}),
    ):
        result = sentiment_sources.fetch_stocktwits_messages("NVDA")
    assert "no StockTwits messages found" in result


def test_stocktwits_truncates_long_body():
    """Single very long message body → truncated to ~280 chars with
    ellipsis so the prompt doesn't blow up."""
    long_text = "x" * 500
    body = {
        "messages": [
            {
                "created_at": "2026-05-13T10:00:00Z",
                "user": {"username": "verbose"},
                "entities": {"sentiment": {"basic": "Bullish"}},
                "body": long_text,
            }
        ]
    }
    with patch(
        "engine.sentiment_sources.urlopen",
        return_value=_mock_urlopen(body),
    ):
        result = sentiment_sources.fetch_stocktwits_messages("NVDA")
    # Ellipsis present + body chopped well under raw length
    assert "…" in result
    assert "x" * 500 not in result


# ---- Reddit ---------------------------------------------------------------


def test_reddit_routes_crypto_to_crypto_subs():
    """asset_class=crypto selects crypto subreddits, not equity ones."""
    calls: list[str] = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        return _mock_urlopen({"data": {"children": []}})

    with patch("engine.sentiment_sources.urlopen", side_effect=fake_urlopen):
        sentiment_sources.fetch_reddit_posts(
            "BTC", asset_class="crypto", inter_request_delay=0
        )
    # Each crypto sub should have been queried
    assert any("r/CryptoCurrency" in c for c in calls)
    assert any("r/CryptoMarkets" in c for c in calls)
    # None of the equity subs
    assert not any("r/wallstreetbets" in c for c in calls)


def test_reddit_routes_equity_to_equity_subs():
    calls: list[str] = []

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        return _mock_urlopen({"data": {"children": []}})

    with patch("engine.sentiment_sources.urlopen", side_effect=fake_urlopen):
        sentiment_sources.fetch_reddit_posts(
            "NVDA", asset_class="equity", inter_request_delay=0
        )
    assert any("r/wallstreetbets" in c for c in calls)
    assert not any("r/CryptoCurrency" in c for c in calls)


def test_reddit_parses_typical_payload():
    """Standard reddit search response shape → formatted plaintext block."""
    body = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "NVDA earnings tomorrow — long calls",
                        "score": 42,
                        "num_comments": 15,
                        "created_utc": 1715961600,  # 2024-05-17
                        "selftext": "I think this prints.",
                    }
                },
                {
                    "data": {
                        "title": "Why I'm short",
                        "score": 7,
                        "num_comments": 3,
                        "created_utc": 1716048000,
                        "selftext": "",
                    }
                },
            ]
        }
    }
    with patch(
        "engine.sentiment_sources.urlopen",
        return_value=_mock_urlopen(body),
    ):
        result = sentiment_sources.fetch_reddit_posts(
            "NVDA", asset_class="equity", inter_request_delay=0
        )
    assert "NVDA earnings tomorrow" in result
    assert "42↑" in result
    assert "15c" in result


def test_reddit_returns_placeholder_when_all_subs_empty():
    """No posts across all subs → consolidated placeholder, not a crash."""
    with patch(
        "engine.sentiment_sources.urlopen",
        return_value=_mock_urlopen({"data": {"children": []}}),
    ):
        result = sentiment_sources.fetch_reddit_posts(
            "ZZZZ", asset_class="equity", inter_request_delay=0
        )
    assert "no Reddit posts found" in result


def test_reddit_swallows_per_sub_errors():
    """One sub failing must not kill the entire fetch — others still
    contribute their (possibly empty) blocks."""
    call_count = {"n": 0}

    def fake_urlopen(req, timeout):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise URLError("first sub down")
        return _mock_urlopen({"data": {"children": []}})

    with patch("engine.sentiment_sources.urlopen", side_effect=fake_urlopen):
        result = sentiment_sources.fetch_reddit_posts(
            "NVDA", asset_class="equity", inter_request_delay=0
        )
    # Three subreddits, first fails — the placeholder block still
    # mentions one of the remaining subs.
    assert "no Reddit posts found" in result or "<no posts found" in result


def test_reddit_truncates_long_selftext():
    """Long self-text → truncated to keep prompt bounded."""
    body = {
        "data": {
            "children": [
                {
                    "data": {
                        "title": "DD on NVDA",
                        "score": 100,
                        "num_comments": 50,
                        "created_utc": 1715961600,
                        "selftext": "y" * 1000,
                    }
                }
            ]
        }
    }
    with patch(
        "engine.sentiment_sources.urlopen",
        return_value=_mock_urlopen(body),
    ):
        result = sentiment_sources.fetch_reddit_posts(
            "NVDA", asset_class="equity", inter_request_delay=0
        )
    assert "y" * 1000 not in result
    assert "…" in result


# ---- Async wrappers -------------------------------------------------------


@pytest.mark.asyncio
async def test_stocktwits_async_wraps_sync():
    body = {"messages": [
        {
            "created_at": "2026-05-13T10:00:00Z",
            "user": {"username": "a"},
            "entities": {"sentiment": {"basic": "Bullish"}},
            "body": "hi",
        }
    ]}
    with patch(
        "engine.sentiment_sources.urlopen",
        return_value=_mock_urlopen(body),
    ):
        result = await sentiment_sources.fetch_stocktwits_messages_async("NVDA")
    assert "Bullish: 1" in result


@pytest.mark.asyncio
async def test_reddit_async_wraps_sync():
    with patch(
        "engine.sentiment_sources.urlopen",
        return_value=_mock_urlopen({"data": {"children": []}}),
    ):
        result = await sentiment_sources.fetch_reddit_posts_async(
            "NVDA", asset_class="equity"
        )
    assert "no Reddit posts" in result
