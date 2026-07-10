"""Codex-backed LangChain chat model — OAuth drives the REAL graph.

The ChatGPT-subscription (OAuth) path talks to the Codex backend:

    https://chatgpt.com/backend-api/codex/responses

which speaks the OpenAI *Responses API* wire shape — the same shape the
upstream library already uses for native OpenAI (`use_responses_api=True`
in `tradingagents/llm_clients/openai_client.py`). So no custom wire code:
a stock `ChatOpenAI` pointed at the Codex base URL with the OAuth bearer
token + Codex headers gives us tool-calling, structured output, and
streaming for free. Verified end-to-end (spike, 2026-07-05): a
`.bind_tools()` round-trip — tool_call out, ToolMessage back, grounded
answer — passes against the live endpoint.

Two endpoint quirks, both discovered in the spike:
  - `stream` MUST be true (400 "Stream must be set to true" otherwise) —
    hence `streaming=True`; LangChain aggregates the SSE stream so
    `.invoke()` callers still get one complete message.
  - `store: false` must be sent (subscription runs are never stored).

Injection strategy: `TradingAgentsGraph.__init__` builds its LLMs through
the module-global `create_llm_client` in `tradingagents/graph/trading_graph.py`.
`codex_factory_patch()` swaps that reference for the duration of the
SYNCHRONOUS graph-construction window (the same window `full_debate` uses
for BYO-key env injection — no await points, so no other coroutine can
observe the patch) and restores it on exit. The `tradingagents/` library
itself stays byte-for-byte pristine.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Optional

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"

# Header set per pi-ai (openai-codex-responses.js: buildBaseCodexHeaders).
# `chatgpt-account-id` is appended per-session; without it Codex 401s.
_CODEX_HEADERS_BASE = {
    "originator": "pi",
    "User-Agent": "pi (TradingAgentsLab)",
    "OpenAI-Beta": "responses=experimental",
}


def _codex_chat_class() -> Any:
    """Build the CodexChatOpenAI class lazily (langchain import deferred —
    the free engine venv doesn't carry it; same reason server.py defers
    full_debate).
    """
    from tradingagents.llm_clients.openai_client import NormalizedChatOpenAI

    def _item_text(item: dict) -> str:
        """Extract plain text from a Responses-API input item's content —
        either a bare string or a list of {"type": "input_text", ...} parts."""
        content = item.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(part, str):
                    parts.append(part)
            return "\n".join(parts)
        return ""

    class CodexChatOpenAI(NormalizedChatOpenAI):
        """Codex-endpoint quirk: system/developer roles are rejected inside
        `input` (400 "System messages are not allowed") — the backend wants
        the system prompt as top-level `instructions`, which is exactly how
        pi-ai sends it. Hoist them out of the payload here; the DeepSeek
        subclass in the library models the same provider-quirk pattern.
        """

        def _get_request_payload(self, input_, *, stop=None, **kwargs):
            payload = super()._get_request_payload(input_, stop=stop, **kwargs)
            items = payload.get("input")
            if isinstance(items, list):
                system_texts: list[str] = []
                rest: list[Any] = []
                for item in items:
                    role = item.get("role") if isinstance(item, dict) else None
                    if role in ("system", "developer"):
                        text = _item_text(item)
                        if text:
                            system_texts.append(text)
                    else:
                        rest.append(item)
                if system_texts:
                    existing = payload.get("instructions") or ""
                    payload["instructions"] = "\n\n".join(
                        t for t in [existing, *system_texts] if t
                    )
                    payload["input"] = rest
            return payload

    return CodexChatOpenAI


def build_codex_llm(
    *,
    model: str,
    access_token: str,
    account_id: str,
    **kwargs: Any,
) -> Any:
    """Build a Codex-backed chat model with the library's normalization.

    Extra `kwargs` are whatever `_get_provider_kwargs` produced for openai
    (`reasoning_effort`, `callbacks`) — all valid ChatOpenAI params, so
    they forward as-is.
    """
    headers = dict(_CODEX_HEADERS_BASE)
    headers["chatgpt-account-id"] = account_id
    return _codex_chat_class()(
        model=model,
        api_key=access_token,
        base_url=CODEX_BASE_URL,
        use_responses_api=True,
        streaming=True,  # Codex mandates SSE; invoke() still aggregates.
        extra_body={"store": False},
        default_headers=headers,
        **kwargs,
    )


class _CodexClientShim:
    """Duck-types the two members of `BaseLLMClient` that
    `TradingAgentsGraph.__init__` actually touches: `get_llm()`.
    """

    def __init__(self, model: str, access_token: str, account_id: str, kwargs: dict):
        self._model = model
        self._access = access_token
        self._account = account_id
        self._kwargs = kwargs

    def get_llm(self) -> Any:
        return build_codex_llm(
            model=self._model,
            access_token=self._access,
            account_id=self._account,
            **self._kwargs,
        )


@contextmanager
def codex_factory_patch(access_token: str, account_id: str) -> Iterator[None]:
    """Route provider="openai" LLM construction through the Codex backend.

    Must wrap ONLY the synchronous `TradingAgentsGraph(...)` construction
    span (mirrors full_debate's env-var window): no awaits inside, patch
    restored in `finally` so a construction failure can't leak the patch
    into a concurrent API-key session.
    """
    from tradingagents.graph import trading_graph as _tg

    original = _tg.create_llm_client

    def _patched(
        provider: str,
        model: str,
        base_url: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        if provider.lower() == "openai":
            return _CodexClientShim(model, access_token, account_id, kwargs)
        return original(provider, model, base_url=base_url, **kwargs)

    _tg.create_llm_client = _patched
    try:
        yield
    finally:
        _tg.create_llm_client = original
