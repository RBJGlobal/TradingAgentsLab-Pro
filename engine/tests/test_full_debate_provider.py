"""Full analysis provider ids and setup failures.

- The app's "gemini" provider reaches the upstream library as "google" (the
  library's factory raises on "gemini"), with the key in GOOGLE_API_KEY only
  during construction.
- A failure while building the graph ends as a run.error event, not an
  exception out of the generator.
- The WebSocket turns a debate generator that raises into a run.error and a
  normal close, instead of dropping the socket (close code 1006).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from engine import full_debate as fd
from engine.server import build_app

TOKEN = "test-token-1234"
GEMINI = "gemini-3.1-flash-lite"


class _CapturingGraph:
    """Records what the library would be built with, then fails setup."""

    seen: dict[str, Any] = {}

    def __init__(self, *, config, **_kw):
        type(self).seen = {
            "provider": config.get("llm_provider"),
            "google_key": os.environ.get("GOOGLE_API_KEY"),
        }
        raise RuntimeError("stop after construction")


async def _drain(gen) -> list[dict]:
    return [e async for e in gen]


def _gemini_config() -> dict[str, Any]:
    return {"llm_provider": "gemini", "deep_think_llm": GEMINI, "quick_think_llm": GEMINI}


def test_gemini_reaches_the_library_as_google(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(fd, "TradingAgentsGraph", _CapturingGraph)
    asyncio.run(_drain(fd.full_debate(
        "NVDA", "2026-11-20", config=_gemini_config(),
        api_key="placeholder-key", auth_kind="api_key",
    )))
    assert _CapturingGraph.seen == {"provider": "google", "google_key": "placeholder-key"}
    # Restored after the construction window.
    assert "GOOGLE_API_KEY" not in os.environ


def test_real_library_accepts_gemini_and_starts():
    """No network: construction only, stopped at graph.plan."""

    async def first_events():
        gen = fd.full_debate(
            "NVDA", "2026-11-20", config=_gemini_config(),
            selected_analysts=["market"], api_key="placeholder-key", auth_kind="api_key",
        )
        out = []
        try:
            async for e in gen:
                out.append(e)
                if e["type"] in ("graph.plan", "run.error"):
                    break
        finally:
            await gen.aclose()
        return out

    types = [e["type"] for e in asyncio.run(first_events())]
    assert types == ["session.start", "graph.plan"]


def test_setup_failure_is_a_run_error_event(monkeypatch):
    monkeypatch.setattr(fd, "TradingAgentsGraph", _CapturingGraph)
    events = asyncio.run(_drain(fd.full_debate(
        "NVDA", "2026-11-20", config=_gemini_config(),
        api_key="placeholder-key", auth_kind="api_key",
    )))
    assert events == [{"type": "run.error",
                       "error": "RuntimeError: stop after construction"}]


@pytest.fixture
def client(tmp_db):
    app = build_app(token=TOKEN)
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {TOKEN}"
        yield c


def test_ws_turns_a_raising_debate_into_run_error(client, monkeypatch):
    from engine import server

    async def _none(**_kw):
        return None

    async def _empty(**_kw):
        return []

    monkeypatch.setattr(server, "_fetch_summary_safe", _none)
    monkeypatch.setattr(server, "_fetch_news_safe", _empty)

    async def raising_full_debate(ticker, trade_date, **_kw):
        raise ValueError("Unsupported LLM provider: example")
        yield {}  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(fd, "full_debate", raising_full_debate)

    received: list[dict] = []
    with client.websocket_connect(f"/stream?token={TOKEN}") as ws:
        ws.send_json({
            "ticker": "NVDA", "trade_date": "2026-11-20", "engine": "pro",
            "pro_config": {"deep_think_llm": GEMINI, "quick_think_llm": GEMINI},
            "provider_config": {"provider": "gemini",
                                "auth": {"type": "api_key", "api_key": "placeholder-key"},
                                "model": GEMINI, "max_tokens": 400},
        })
        with pytest.raises(Exception) as closed:
            while True:
                received.append(ws.receive_json())
    assert received[-1] == {"type": "run.error",
                            "error": "ValueError: Unsupported LLM provider: example"}
    assert getattr(closed.value, "code", None) == 1000
