"""Tests for the local LLM adapter + detection probe.

Detection tests stub httpx to avoid real localhost network calls — CI
won't have Ollama running and we don't want the suite to depend on
ephemeral developer-machine state. Adapter tests verify the base_url
override threads through to the AsyncOpenAI client kwargs.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine import local_llm_detect
from engine.llm_providers import (
    LocalLLMAdapter,
    OpenAIAdapter,
    ProviderConfig,
    adapter_for,
)


# ---- LocalLLMAdapter ------------------------------------------------------


def test_local_adapter_subclasses_openai():
    """Inheritance preserves the OpenAI Chat Completions request path."""
    a = LocalLLMAdapter(base_url="http://localhost:11434/v1")
    assert isinstance(a, OpenAIAdapter)
    assert a.name == "local"


def test_local_adapter_threads_base_url_into_client():
    """`open()` must pass base_url to AsyncOpenAI so requests hit the
    user's local runtime, not OpenAI's cloud."""
    a = LocalLLMAdapter(base_url="http://localhost:11434/v1")

    with patch("openai.AsyncOpenAI") as mock_client:
        import asyncio

        asyncio.run(a.open(api_key="anything"))

        mock_client.assert_called_once()
        kwargs = mock_client.call_args.kwargs
        assert kwargs["base_url"] == "http://localhost:11434/v1"
        assert kwargs["api_key"] == "anything"


def test_local_adapter_uses_generous_read_timeout():
    """Local inference (cold load / CPU / large models) can take minutes, so
    the local adapter must NOT inherit the tight 90s cloud read timeout — that
    would kill valid local debates."""
    import httpx

    a = LocalLLMAdapter(base_url="http://localhost:11434/v1")
    with patch("openai.AsyncOpenAI") as mock_client:
        import asyncio

        asyncio.run(a.open(api_key="anything"))
        timeout = mock_client.call_args.kwargs.get("timeout")
        assert isinstance(timeout, httpx.Timeout)
        # Comfortably longer than the cloud 90s — minutes, for slow local runs.
        assert timeout.read is not None and timeout.read >= 300


def test_openai_adapter_sets_request_timeout():
    """The API-key OpenAI client must be constructed with an explicit timeout.
    Without it the SDK defaults to a 600s read timeout, so a stalled provider
    would freeze a debate (and its WebSocket) for minutes per agent."""
    import httpx

    a = OpenAIAdapter()
    with patch("openai.AsyncOpenAI") as mock_client:
        import asyncio

        asyncio.run(a.open(api_key="sk-test"))

        kwargs = mock_client.call_args.kwargs
        timeout = kwargs.get("timeout")
        assert isinstance(timeout, httpx.Timeout)
        # Read timeout must be a finite, sane bound (not the 600s default).
        assert timeout.read is not None and timeout.read <= 120


def test_local_adapter_factory_picks_right_class():
    """`adapter_for` must return LocalLLMAdapter for the local provider
    and thread the base_url through."""
    config = ProviderConfig(
        provider="local",
        auth={"type": "local", "base_url": "http://localhost:1234/v1"},
        model="llama3.2:latest",
        max_tokens=400,
    )
    a = adapter_for(config)
    assert isinstance(a, LocalLLMAdapter)
    assert a._base_url == "http://localhost:1234/v1"


# ---- ProviderConfig.from_dict (local branch) -----------------------------


def test_provider_config_accepts_local_auth():
    config = ProviderConfig.from_dict(
        {
            "provider": "local",
            "auth": {"type": "local", "base_url": "http://localhost:11434/v1"},
            "model": "llama3.2:latest",
        }
    )
    assert config is not None
    assert config.provider == "local"
    assert config.auth["type"] == "local"
    assert config.auth["base_url"] == "http://localhost:11434/v1"
    assert config.model == "llama3.2:latest"


def test_provider_config_rejects_local_without_base_url():
    """Empty base_url drops the config — better to fall through to the
    stub than ship a half-configured request."""
    config = ProviderConfig.from_dict(
        {
            "provider": "local",
            "auth": {"type": "local", "base_url": ""},
            "model": "llama3.2",
        }
    )
    assert config is None


def test_provider_config_rejects_local_provider_with_api_key_auth():
    """Catch the cross-talk mistake: provider=local with auth.type=api_key
    is a renderer bug. Drop it loud."""
    config = ProviderConfig.from_dict(
        {
            "provider": "local",
            "auth": {"type": "api_key", "api_key": "sk-fake"},
            "model": "llama3.2",
        }
    )
    assert config is None


def test_provider_config_rejects_openai_provider_with_local_auth():
    """And the reverse — local auth with provider=openai. Avoids silently
    routing an OpenAI request to an arbitrary localhost URL."""
    config = ProviderConfig.from_dict(
        {
            "provider": "openai",
            "auth": {"type": "local", "base_url": "http://localhost:11434/v1"},
            "model": "gpt-4o-mini",
        }
    )
    assert config is None


def test_provider_config_local_bearer_token_is_sentinel():
    """Local runtimes accept any non-empty Authorization header. We
    return a fixed "local" sentinel so callers don't pass empty string
    (which AsyncOpenAI rejects)."""
    config = ProviderConfig(
        provider="local",
        auth={"type": "local", "base_url": "http://localhost:11434/v1"},
        model="llama3.2",
    )
    assert config.bearer_token == "local"
    assert config.auth_kind == "local"


# ---- local_llm_detect.detect_runtimes -------------------------------------


@pytest.mark.asyncio
async def test_detect_returns_empty_when_nothing_running():
    """All probes fail → empty list, NOT an exception. Empty is a valid
    state (user hasn't installed any local runtime yet)."""
    # Stub httpx.AsyncClient.get to always raise ConnectError.
    import httpx

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            raise httpx.ConnectError("connection refused")

    with patch.object(httpx, "AsyncClient", lambda *a, **kw: FailingClient()):
        result = await local_llm_detect.detect_runtimes()

    assert result == []


@pytest.mark.asyncio
async def test_detect_parses_openai_compat_response():
    """Ollama / LM Studio return `{data: [{id, ...}, ...]}` on /v1/models.
    Parser extracts the id list in order."""
    sample_body = {
        "object": "list",
        "data": [
            {"id": "llama3.2:latest", "object": "model"},
            {"id": "qwen2.5:7b", "object": "model"},
        ],
    }

    class SuccessClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            # Respond success on the first probe (Ollama), fail others
            # to keep the test focused.
            resp = MagicMock()
            if "11434" in url:
                resp.status_code = 200
                resp.json = MagicMock(return_value=sample_body)
            else:
                resp.status_code = 404
                resp.json = MagicMock(return_value={})
            return resp

    import httpx

    with patch.object(httpx, "AsyncClient", SuccessClient):
        result = await local_llm_detect.detect_runtimes()

    assert len(result) == 1
    r = result[0]
    assert r.runtime == "Ollama"
    assert r.base_url == "http://localhost:11434/v1"
    assert r.models == ["llama3.2:latest", "qwen2.5:7b"]


@pytest.mark.asyncio
async def test_detect_skips_runtime_with_zero_models():
    """A runtime that responds 200 with an empty model list isn't useful
    — the dropdown would be empty. Treat as not-detected so we don't
    surface a broken row in the UI."""
    empty_body = {"object": "list", "data": []}

    class EmptyClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            resp = MagicMock()
            resp.status_code = 200
            resp.json = MagicMock(return_value=empty_body)
            return resp

    import httpx

    with patch.object(httpx, "AsyncClient", EmptyClient):
        result = await local_llm_detect.detect_runtimes()

    assert result == []


def test_extract_models_ignores_malformed_entries():
    """Defensive: a runtime that returns garbage entries shouldn't crash
    the parser. Non-string ids and missing ids are skipped."""
    body = {
        "data": [
            {"id": "valid:model"},
            {"id": None},  # garbage
            {"id": ""},  # empty
            {"not_id": "x"},  # malformed
            {"id": "also-valid"},
        ]
    }
    models = local_llm_detect._extract_models(body)
    assert models == ["valid:model", "also-valid"]


def test_extract_models_handles_non_dict_body():
    """Defensive: shape drift in the runtime's response shouldn't crash."""
    assert local_llm_detect._extract_models([1, 2, 3]) == []
    assert local_llm_detect._extract_models(None) == []
    assert local_llm_detect._extract_models("garbage") == []


def test_runtime_to_dict_round_trips():
    """Serializer produces stable JSON-able dict for the HTTP wire."""
    r = local_llm_detect.DetectedRuntime(
        runtime="Ollama",
        base_url="http://localhost:11434/v1",
        models=["a", "b"],
    )
    d = local_llm_detect.runtime_to_dict(r)
    # JSON-able + matches the renderer's `LocalRuntime` interface shape.
    assert json.dumps(d)  # would raise on non-serializable
    assert d == {
        "runtime": "Ollama",
        "base_url": "http://localhost:11434/v1",
        "models": ["a", "b"],
    }
