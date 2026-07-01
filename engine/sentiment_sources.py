"""Social-sentiment fetchers — StockTwits + Reddit.

Pre-fetches structured social signal so the sentiment_analyst agent has
real data to ground in instead of fabricating. Ported from
TauricResearch/TradingAgents commit `0fcf136` (sentiment_analyst
integration). Both endpoints are no-auth public JSON — fits our zero-
data-collection posture: no API keys, no user identifiers leave the
machine, only the ticker symbol goes outbound.

Why ports + adapt vs use upstream's modules directly: upstream's modules
are pulled into a LangGraph orchestration we don't use, and they ship
under Apache 2.0 + the upstream's logger/UA conventions. Re-implementing
keeps our engine sidecar free of upstream's tradingagents-package
plumbing and lets us use our own logging/UA strings. Both functions
return formatted plaintext blocks ready to inject directly into our
agent prompts.

Crypto support: StockTwits uses cashtags like `$BTC.X` for crypto
(returns the same shape as equity streams). Reddit search just takes
any string — we send the ticker's `base` symbol (e.g. "BTC", "ETH"),
which surfaces the right discussion threads naturally.

Failure mode: BOTH functions return a placeholder string on any error
(network / parse / shape drift) rather than raising. The agent always
sees a string — either real data or a clear "<unavailable>" marker —
so it can produce a useful response even when one source is offline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Polite UA string identifying us to public endpoints. Both StockTwits
# and Reddit serve any UA; the courtesy header lets them rate-limit us
# specifically if we misbehave, instead of taking down the user-agent
# class globally.
_UA = "TradingAgentsLab/0.1 (+https://github.com/RBJGlobal/TradingAgentsLab)"

# Short timeouts — sentiment is supplemental signal; a slow fetch must
# never block the debate. The agent prompt always sees the placeholder
# if we time out.
_STOCKTWITS_TIMEOUT_S = 6.0
_REDDIT_TIMEOUT_S = 6.0


# ---- StockTwits ----------------------------------------------------------


_STOCKTWITS_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"


def fetch_stocktwits_messages(
    ticker: str, *, limit: int = 30, timeout: float = _STOCKTWITS_TIMEOUT_S
) -> str:
    """Fetch recent StockTwits messages for `ticker` and return a formatted
    plaintext block ready for prompt injection.

    Returns a placeholder when the endpoint is unreachable, the symbol
    has no messages, or the response shape is unexpected — the caller
    never has to special-case None or exceptions.

    For crypto tickers, pass the base symbol (e.g. "BTC", "ETH") —
    StockTwits exposes crypto streams at the same URL using cashtag
    semantics.
    """
    url = _STOCKTWITS_API.format(ticker=ticker.upper())
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — public no-auth
            data = json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("StockTwits fetch failed for %s: %s", ticker, exc)
        return f"<stocktwits unavailable: {type(exc).__name__}>"

    messages = data.get("messages", []) if isinstance(data, dict) else []
    if not messages:
        return f"<no StockTwits messages found for ${ticker.upper()}>"

    lines: list[str] = []
    bullish = bearish = unlabeled = 0
    for m in messages[:limit]:
        created = m.get("created_at", "")
        user = (m.get("user") or {}).get("username", "?")
        entities = m.get("entities") or {}
        sentiment_obj = entities.get("sentiment") or {}
        sentiment = (
            sentiment_obj.get("basic")
            if isinstance(sentiment_obj, dict)
            else None
        )
        body = (m.get("body") or "").replace("\n", " ").strip()
        if len(body) > 280:
            body = body[:280] + "…"

        if sentiment == "Bullish":
            bullish += 1
            tag = "Bullish"
        elif sentiment == "Bearish":
            bearish += 1
            tag = "Bearish"
        else:
            unlabeled += 1
            tag = "no-label"
        lines.append(f"[{created} · @{user} · {tag}] {body}")

    total = bullish + bearish + unlabeled
    bull_pct = round(100 * bullish / total) if total else 0
    bear_pct = round(100 * bearish / total) if total else 0
    summary = (
        f"Bullish: {bullish} ({bull_pct}%) · "
        f"Bearish: {bearish} ({bear_pct}%) · "
        f"Unlabeled: {unlabeled} · "
        f"Total: {total} most-recent messages"
    )
    return summary + "\n\n" + "\n".join(lines)


# ---- Reddit ---------------------------------------------------------------


_REDDIT_API = "https://www.reddit.com/r/{sub}/search.json?{qs}"

# Subreddits ordered roughly by signal density for ticker-specific
# discussion. wallstreetbets has the most volume but most noise;
# stocks / investing trend more measured. Caller can override.
DEFAULT_EQUITY_SUBREDDITS = ("wallstreetbets", "stocks", "investing")

# Crypto talk lives in different subs than equities. Same total fetch
# budget so the prompt cost stays bounded.
DEFAULT_CRYPTO_SUBREDDITS = ("CryptoCurrency", "CryptoMarkets", "Bitcoin")


def _subreddits_for_asset_class(asset_class: str) -> tuple[str, ...]:
    """Pick the right subreddit list based on asset class.

    Equity tickers in r/CryptoCurrency are mostly noise (and vice versa)
    — routing pays off in signal density even at the same fetch budget.
    """
    if asset_class == "crypto":
        return DEFAULT_CRYPTO_SUBREDDITS
    return DEFAULT_EQUITY_SUBREDDITS


def _fetch_subreddit(
    ticker: str,
    sub: str,
    *,
    limit: int,
    timeout: float,
) -> list[dict]:
    qs = urlencode(
        {
            "q": ticker,
            "restrict_sr": "on",
            "sort": "new",
            "t": "week",  # last 7 days
            "limit": limit,
        }
    )
    url = _REDDIT_API.format(sub=sub, qs=qs)
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — public no-auth
            payload = json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Reddit fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return []
    children = (payload.get("data") or {}).get("children") or []
    return [c.get("data", {}) for c in children if isinstance(c, dict)]


def fetch_reddit_posts(
    ticker: str,
    *,
    subreddits: Iterable[str] | None = None,
    asset_class: str = "equity",
    limit_per_sub: int = 5,
    timeout: float = _REDDIT_TIMEOUT_S,
    inter_request_delay: float = 0.4,
) -> str:
    """Fetch recent Reddit posts mentioning `ticker` across finance
    subreddits and return a formatted plaintext block.

    `subreddits` overrides the asset-class default. `inter_request_delay`
    keeps us under Reddit's public rate limit (~10 req/min per IP) even
    if the caller queries many subreddits.
    """
    subs: tuple[str, ...] = (
        tuple(subreddits)
        if subreddits is not None
        else _subreddits_for_asset_class(asset_class)
    )
    blocks: list[str] = []
    total_posts = 0
    for i, sub in enumerate(subs):
        if i > 0:
            time.sleep(inter_request_delay)
        posts = _fetch_subreddit(ticker, sub, limit=limit_per_sub, timeout=timeout)
        total_posts += len(posts)
        if not posts:
            blocks.append(
                f"r/{sub}: <no posts found mentioning {ticker.upper()} "
                f"in the past 7 days>"
            )
            continue

        lines = [
            f"r/{sub} — {len(posts)} recent posts mentioning {ticker.upper()}:"
        ]
        for p in posts:
            title = (p.get("title") or "").replace("\n", " ").strip()
            score = p.get("score", 0)
            comments = p.get("num_comments", 0)
            created = p.get("created_utc")
            created_str = (
                time.strftime("%Y-%m-%d", time.gmtime(created))
                if created
                else "?"
            )
            selftext = (p.get("selftext") or "").replace("\n", " ").strip()
            if len(selftext) > 240:
                selftext = selftext[:240] + "…"
            lines.append(
                f"  [{created_str} · {score:>4}↑ · {comments:>3}c] {title}"
                + (f"\n    body excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        return (
            f"<no Reddit posts found mentioning {ticker.upper()} across "
            f"{', '.join(f'r/{s}' for s in subs)} in the past 7 days>"
        )
    return "\n\n".join(blocks)


# ---- Async wrappers -------------------------------------------------------
#
# The engine's live_debate is fully async; running these blocking urllib
# fetchers on the asyncio thread would stall the WS event pump for
# seconds. asyncio.to_thread offloads to a worker — fast, simple, no
# need to bring in an httpx-based rewrite.


async def fetch_stocktwits_messages_async(
    ticker: str, *, limit: int = 30
) -> str:
    return await asyncio.to_thread(
        fetch_stocktwits_messages, ticker, limit=limit
    )


async def fetch_reddit_posts_async(
    ticker: str,
    *,
    asset_class: str = "equity",
    limit_per_sub: int = 5,
) -> str:
    return await asyncio.to_thread(
        fetch_reddit_posts,
        ticker,
        asset_class=asset_class,
        limit_per_sub=limit_per_sub,
    )


__all__ = [
    "fetch_stocktwits_messages",
    "fetch_reddit_posts",
    "fetch_stocktwits_messages_async",
    "fetch_reddit_posts_async",
    "DEFAULT_EQUITY_SUBREDDITS",
    "DEFAULT_CRYPTO_SUBREDDITS",
]
