"""Ticker normalization — single source of truth for asset-class detection
and per-provider symbol canonicalization.

Users type tickers loosely: "BTC", "btc", "BTC-USD", "BTC/USD", "Bitcoin".
Each data provider expects its own format. Normalize once, route everywhere.

## Canonical forms

| User input    | asset_class | display   | yfinance | alpaca   |
|---------------|-------------|-----------|----------|----------|
| NVDA          | equity      | NVDA      | NVDA     | NVDA     |
| nvda          | equity      | NVDA      | NVDA     | NVDA     |
| BTC           | crypto      | BTC/USD   | BTC-USD  | BTC/USD  |
| BTC-USD       | crypto      | BTC/USD   | BTC-USD  | BTC/USD  |
| BTC/USD       | crypto      | BTC/USD   | BTC-USD  | BTC/USD  |
| ETH/USDT      | crypto      | ETH/USDT  | ETH-USD* | ETH/USDT |

(* yfinance has limited stablecoin pair support — we degrade USDT/USDC pairs
to USD pair for yfinance, since it's the closest equivalent. Alpaca handles
the exact pair.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

AssetClass = Literal["equity", "crypto"]

# Symbols we know are crypto. Extend as needed — being in this list means
# bare "BTC" gets treated as the crypto, not as an equity ticker. We picked
# the top-cap names where there's negligible US-equity ambiguity.
_KNOWN_CRYPTO_BASES = frozenset({
    "BTC", "ETH", "USDT", "USDC", "BNB", "XRP", "SOL", "ADA", "AVAX",
    "DOGE", "SHIB", "MATIC", "DOT", "LINK", "TRX", "NEAR", "ATOM",
    "ALGO", "FIL", "AAVE", "UNI", "CRV", "MKR", "COMP", "SNX",
    "LTC", "BCH", "XLM", "ETC", "XMR", "TON", "OP", "ARB", "PEPE",
    "WIF", "BONK", "TAO", "INJ", "SUI", "APT", "STX", "RNDR",
})

# Quote currencies we recognize for explicit crypto pair input. USD is the
# fallback for bare crypto symbols.
_KNOWN_QUOTES = frozenset({"USD", "USDT", "USDC", "EUR", "GBP", "BTC"})


@dataclass(frozen=True)
class TickerSpec:
    """Normalized ticker info — canonical names per provider."""

    raw: str                 # original user input, lightly trimmed
    asset_class: AssetClass
    base: str                # base symbol uppercase (NVDA, BTC, ETH)
    quote: str               # quote currency uppercase (USD by default; "" for equities)
    display: str             # canonical display form (NVDA or BTC/USD)
    yfinance_symbol: str     # what to pass to yfinance.Ticker(...)
    alpaca_symbol: str       # what to send to Alpaca's API


def normalize_ticker(raw: str) -> TickerSpec:
    """Normalize a free-form user-typed ticker to a TickerSpec.

    Crypto-detection rules (first match wins):
    1. Contains "/" → crypto pair, parse base/quote
    2. Contains "-USD"/"-USDT"/"-USDC" suffix → crypto pair (yfinance form)
    3. Bare base symbol matches known-crypto list → crypto, default quote USD
    4. Otherwise → equity
    """
    if not raw or not raw.strip():
        raise ValueError("ticker required")
    cleaned = raw.strip().upper()

    # Rule 1: explicit "/" pair (Alpaca form)
    if "/" in cleaned:
        parts = cleaned.split("/", 1)
        base, quote = parts[0], parts[1]
        if not base or not quote:
            raise ValueError(f"malformed ticker pair: {raw!r}")
        return _crypto_spec(raw=raw, base=base, quote=quote)

    # Rule 2: "-USD" / "-USDT" / "-USDC" / "-EUR" suffix (yfinance form)
    m = re.match(r"^([A-Z0-9]+)-(USD|USDT|USDC|EUR|GBP|BTC)$", cleaned)
    if m:
        base, quote = m.group(1), m.group(2)
        return _crypto_spec(raw=raw, base=base, quote=quote)

    # Rule 3: bare known-crypto symbol → assume USD pair
    if cleaned in _KNOWN_CRYPTO_BASES:
        return _crypto_spec(raw=raw, base=cleaned, quote="USD")

    # Rule 4: otherwise treat as equity. Validate equity-ish shape.
    if not re.match(r"^[A-Z][A-Z0-9.\-]{0,9}$", cleaned):
        raise ValueError(f"not a valid equity or crypto ticker: {raw!r}")
    return TickerSpec(
        raw=raw,
        asset_class="equity",
        base=cleaned,
        quote="",
        display=cleaned,
        yfinance_symbol=cleaned,
        alpaca_symbol=cleaned,
    )


def _crypto_spec(*, raw: str, base: str, quote: str) -> TickerSpec:
    if quote not in _KNOWN_QUOTES:
        raise ValueError(
            f"unsupported quote currency {quote!r} in {raw!r}; "
            f"expected one of {sorted(_KNOWN_QUOTES)}"
        )
    # yfinance only supports the USD pair reliably for most assets.
    # Stablecoin pairs (USDT/USDC) collapse to the USD pair for yfinance —
    # it's the closest equivalent. Alpaca gets the exact pair.
    yf_quote = "USD" if quote in {"USDT", "USDC"} else quote
    return TickerSpec(
        raw=raw,
        asset_class="crypto",
        base=base,
        quote=quote,
        display=f"{base}/{quote}",
        yfinance_symbol=f"{base}-{yf_quote}",
        alpaca_symbol=f"{base}/{quote}",
    )


__all__ = [
    "AssetClass",
    "TickerSpec",
    "normalize_ticker",
]
