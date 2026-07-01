"""Ticker normalization tests — covers asset-class detection and per-provider
canonical symbol generation."""

from __future__ import annotations

import pytest

from engine.ticker import normalize_ticker


# ---- Equities ---------------------------------------------------------------


def test_normalize_uppercase_equity():
    spec = normalize_ticker("NVDA")
    assert spec.asset_class == "equity"
    assert spec.base == "NVDA"
    assert spec.quote == ""
    assert spec.display == "NVDA"
    assert spec.yfinance_symbol == "NVDA"
    assert spec.alpaca_symbol == "NVDA"


def test_normalize_lowercase_equity_uppercased():
    spec = normalize_ticker("aapl")
    assert spec.asset_class == "equity"
    assert spec.display == "AAPL"


def test_normalize_equity_with_dot():
    """e.g. BRK.A — equity tickers can have dots."""
    spec = normalize_ticker("BRK.A")
    assert spec.asset_class == "equity"
    assert spec.display == "BRK.A"


# ---- Crypto: bare known symbol → assume USD pair ---------------------------


def test_normalize_bare_btc_is_crypto_with_usd_quote():
    spec = normalize_ticker("BTC")
    assert spec.asset_class == "crypto"
    assert spec.base == "BTC"
    assert spec.quote == "USD"
    assert spec.display == "BTC/USD"
    assert spec.yfinance_symbol == "BTC-USD"
    assert spec.alpaca_symbol == "BTC/USD"


def test_normalize_bare_eth_is_crypto():
    spec = normalize_ticker("eth")
    assert spec.asset_class == "crypto"
    assert spec.display == "ETH/USD"


def test_normalize_bare_sol_is_crypto():
    spec = normalize_ticker("sol")
    assert spec.asset_class == "crypto"
    assert spec.alpaca_symbol == "SOL/USD"


# ---- Crypto: explicit slash form (Alpaca style) ---------------------------


def test_normalize_btc_usd_slash():
    spec = normalize_ticker("BTC/USD")
    assert spec.asset_class == "crypto"
    assert spec.base == "BTC"
    assert spec.quote == "USD"
    assert spec.display == "BTC/USD"
    assert spec.yfinance_symbol == "BTC-USD"
    assert spec.alpaca_symbol == "BTC/USD"


def test_normalize_eth_usdt_slash():
    """Stablecoin pair — yfinance falls back to USD pair, Alpaca gets USDT."""
    spec = normalize_ticker("ETH/USDT")
    assert spec.asset_class == "crypto"
    assert spec.display == "ETH/USDT"
    assert spec.yfinance_symbol == "ETH-USD"  # USDT collapses to USD for yfinance
    assert spec.alpaca_symbol == "ETH/USDT"


def test_normalize_eth_btc_slash():
    """ETH/BTC — non-USD quote pair."""
    spec = normalize_ticker("ETH/BTC")
    assert spec.asset_class == "crypto"
    assert spec.display == "ETH/BTC"
    assert spec.yfinance_symbol == "ETH-BTC"
    assert spec.alpaca_symbol == "ETH/BTC"


# ---- Crypto: dash form (yfinance style) -----------------------------------


def test_normalize_btc_usd_dash():
    spec = normalize_ticker("BTC-USD")
    assert spec.asset_class == "crypto"
    assert spec.base == "BTC"
    assert spec.quote == "USD"
    assert spec.display == "BTC/USD"
    assert spec.yfinance_symbol == "BTC-USD"
    assert spec.alpaca_symbol == "BTC/USD"


def test_normalize_eth_usdc_dash():
    spec = normalize_ticker("ETH-USDC")
    assert spec.asset_class == "crypto"
    assert spec.alpaca_symbol == "ETH/USDC"
    assert spec.yfinance_symbol == "ETH-USD"  # USDC collapses too


# ---- Edge cases -----------------------------------------------------------


def test_normalize_rejects_empty_string():
    with pytest.raises(ValueError):
        normalize_ticker("")
    with pytest.raises(ValueError):
        normalize_ticker("   ")


def test_normalize_rejects_unsupported_quote_currency():
    with pytest.raises(ValueError):
        normalize_ticker("BTC/JPY")


def test_normalize_rejects_malformed_pair():
    with pytest.raises(ValueError):
        normalize_ticker("/USD")
    with pytest.raises(ValueError):
        normalize_ticker("BTC/")


def test_normalize_rejects_lowercase_first_char_after_strip():
    """Leading numeric + non-equity-ish input that looks malformed."""
    with pytest.raises(ValueError):
        normalize_ticker("123-456")


def test_normalize_strips_whitespace():
    spec = normalize_ticker("  NVDA  ")
    assert spec.display == "NVDA"


def test_normalize_unknown_uppercase_treated_as_equity():
    """Three-letter ticker not in known-crypto list → assumed equity."""
    spec = normalize_ticker("XYZ")
    assert spec.asset_class == "equity"
    assert spec.display == "XYZ"
