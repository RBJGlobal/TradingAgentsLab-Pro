"""Tier 2 retry/backoff tests for _complete_with_retry.

Covers the four behaviors the Tier 2 PR ships against:

1. Succeed-after-N: a transient error followed by a clean call resolves.
2. Exhaust-after-N+1: max attempts is bounded; persistent errors raise.
3. No-retry-on-non-transient: a 401 must not waste quota on retries.
4. Honors Retry-After: provider's hint overrides the backoff schedule.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from engine.live_debate import _complete_with_retry, _is_retryable, _retry_after_seconds


# ---- Helpers ---------------------------------------------------------------


class _FakeAdapter:
    """Minimal adapter that records call count and replays a scripted sequence
    of side-effects (exception or success tuple) per call."""

    def __init__(self, script: list):
        self._script = list(script)
        self.calls = 0

    async def complete(self, **_kwargs) -> tuple[str, int, int]:
        self.calls += 1
        if not self._script:
            raise RuntimeError("script exhausted")
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _http_response(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return httpx.Response(status_code=status, headers=headers)


class _StatusError(Exception):
    """Mimics provider-SDK exception shape (`status_code` attr + `response`)."""

    def __init__(self, status_code: int, retry_after: str | None = None):
        super().__init__(f"http {status_code}")
        self.status_code = status_code
        self.response = _http_response(status_code, retry_after)


# ---- _is_retryable + _retry_after_seconds ---------------------------------


def test_is_retryable_httpx_timeouts():
    assert _is_retryable(httpx.ConnectTimeout("connect"))
    assert _is_retryable(httpx.ReadTimeout("read"))
    assert _is_retryable(httpx.ConnectError("conn"))
    assert _is_retryable(httpx.ReadError("read"))


def test_is_retryable_status_codes():
    assert _is_retryable(_StatusError(429))
    assert _is_retryable(_StatusError(500))
    assert _is_retryable(_StatusError(502))
    assert _is_retryable(_StatusError(503))
    assert _is_retryable(_StatusError(504))


def test_is_retryable_skips_client_errors():
    # 401/403/404/422 are caller bugs; retrying just burns quota.
    assert not _is_retryable(_StatusError(401))
    assert not _is_retryable(_StatusError(403))
    assert not _is_retryable(_StatusError(404))
    assert not _is_retryable(_StatusError(422))


def test_is_retryable_codex_runtime_errors():
    # Codex adapter raises RuntimeError with a "Codex <status>: ..." prefix.
    assert _is_retryable(RuntimeError("Codex 503: service unavailable"))
    assert _is_retryable(RuntimeError("Codex 429: rate limited"))
    assert _is_retryable(RuntimeError("Codex stream failed: ReadError"))
    # Non-retryable status codes are NOT retried even via the Codex path.
    assert not _is_retryable(RuntimeError("Codex 400: bad request"))
    assert not _is_retryable(RuntimeError("plain RuntimeError"))


def test_retry_after_seconds_parses_numeric_header():
    assert _retry_after_seconds(_StatusError(429, retry_after="7")) == 7.0
    assert _retry_after_seconds(_StatusError(429, retry_after="2.5")) == 2.5


def test_retry_after_seconds_ignores_non_numeric():
    # Anthropic occasionally sends HTTP-date; we fall through to backoff.
    assert _retry_after_seconds(_StatusError(429, retry_after="Wed, 21 Oct 2026 07:28:00 GMT")) is None
    assert _retry_after_seconds(_StatusError(429, retry_after="")) is None
    assert _retry_after_seconds(RuntimeError("no response attr")) is None


# ---- _complete_with_retry --------------------------------------------------


@pytest.mark.asyncio
async def test_succeeds_after_transient_error(monkeypatch):
    adapter = _FakeAdapter([_StatusError(503), ("hello", 10, 5)])
    # Skip the actual sleep so the test isn't slow.
    monkeypatch.setattr("engine.live_debate.asyncio.sleep", AsyncMock())

    result = await _complete_with_retry(
        adapter,
        provider="openai",
        system="s",
        user="u",
        model="gpt-4o-mini",
        max_tokens=400,
    )
    assert result == ("hello", 10, 5)
    assert adapter.calls == 2


@pytest.mark.asyncio
async def test_exhausts_after_max_attempts(monkeypatch):
    adapter = _FakeAdapter([_StatusError(503), _StatusError(503), _StatusError(503)])
    monkeypatch.setattr("engine.live_debate.asyncio.sleep", AsyncMock())

    with pytest.raises(_StatusError):
        await _complete_with_retry(
            adapter,
            provider="openai",
            system="s",
            user="u",
            model="gpt-4o-mini",
            max_tokens=400,
        )
    assert adapter.calls == 3


@pytest.mark.asyncio
async def test_no_retry_on_401(monkeypatch):
    adapter = _FakeAdapter([_StatusError(401)])
    sleep_mock = AsyncMock()
    monkeypatch.setattr("engine.live_debate.asyncio.sleep", sleep_mock)

    with pytest.raises(_StatusError):
        await _complete_with_retry(
            adapter,
            provider="openai",
            system="s",
            user="u",
            model="gpt-4o-mini",
            max_tokens=400,
        )
    assert adapter.calls == 1
    sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_honors_retry_after_header(monkeypatch):
    adapter = _FakeAdapter([_StatusError(429, retry_after="3"), ("ok", 1, 1)])
    sleep_mock = AsyncMock()
    monkeypatch.setattr("engine.live_debate.asyncio.sleep", sleep_mock)

    await _complete_with_retry(
        adapter,
        provider="openai",
        system="s",
        user="u",
        model="gpt-4o-mini",
        max_tokens=400,
    )
    # First (and only) sleep should equal the Retry-After value, not the
    # exponential schedule (1s base).
    sleep_mock.assert_awaited_once()
    awaited_delay = sleep_mock.await_args.args[0]
    assert awaited_delay == 3.0


@pytest.mark.asyncio
async def test_local_provider_skips_retry(monkeypatch):
    # Local runtimes own their own retry (OpenAI SDK builtin); adding ours
    # burns the user's hardware time. One attempt and propagate.
    adapter = _FakeAdapter([_StatusError(503)])
    sleep_mock = AsyncMock()
    monkeypatch.setattr("engine.live_debate.asyncio.sleep", sleep_mock)

    with pytest.raises(_StatusError):
        await _complete_with_retry(
            adapter,
            provider="local",
            system="s",
            user="u",
            model="llama3.2",
            max_tokens=400,
        )
    assert adapter.calls == 1
    sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_propagates_without_retry(monkeypatch):
    # WS disconnect / generator teardown raises CancelledError; we must
    # propagate immediately so the outer try/finally in live_debate runs.
    adapter = _FakeAdapter([asyncio.CancelledError()])
    sleep_mock = AsyncMock()
    monkeypatch.setattr("engine.live_debate.asyncio.sleep", sleep_mock)

    with pytest.raises(asyncio.CancelledError):
        await _complete_with_retry(
            adapter,
            provider="openai",
            system="s",
            user="u",
            model="gpt-4o-mini",
            max_tokens=400,
        )
    assert adapter.calls == 1
    sleep_mock.assert_not_awaited()
