"""Local LLM runtime detection.

Probes well-known localhost ports for running OpenAI-compatible LLM
runtimes — Ollama, LM Studio, llama.cpp's server. Returns each detected
runtime's base URL + the list of models it exposes.

We deliberately do NOT scan the filesystem for `.gguf` files. A model
file on disk without a runtime cannot be invoked from our engine — we'd
need to spawn llama.cpp ourselves, which is a huge native dependency.
The realistic auto-detection target is "user has Ollama / LM Studio
running"; both expose well-known endpoints and both are OpenAI-compatible.

Design notes:
- All probes have a tight per-runtime timeout (1.5s) so an unreachable
  port can't stall the renderer's Settings page mount.
- Probes run in parallel (asyncio.gather) — total wall time ≤ ~1.5s even
  with all probes failing.
- 404 / connection refused / timeout are all "not detected" — we don't
  distinguish between "runtime not installed" and "runtime offline".
- The renderer caches the result for the Settings page lifetime and
  exposes a Refresh button for manual re-detection.

Add a new runtime: append to `_RUNTIME_PROBES` with the runtime's
well-known port and the OpenAI-compatible `/v1/models` path (or its
non-standard equivalent). The probe shape must return `models: list[str]`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional


# Per-probe timeout. Local runtimes respond in tens of milliseconds when
# online; 1.5s is conservative but still keeps the worst-case wall time
# (all probes failing) bounded for the Settings page.
_PROBE_TIMEOUT_S = 1.5


@dataclass(frozen=True)
class DetectedRuntime:
    """A detected local LLM runtime + the models it exposes.

    `base_url` is the OpenAI-compatible chat-completions root (i.e. the
    string that the OpenAI SDK accepts as `base_url=` and appends
    `/chat/completions` to). For Ollama: "http://localhost:11434/v1".
    """

    runtime: str       # "Ollama", "LM Studio", etc.
    base_url: str
    models: list[str]  # ordered as the runtime returned them


@dataclass(frozen=True)
class _RuntimeProbe:
    name: str           # display name
    base_url: str       # OpenAI-compatible base
    models_path: str    # path relative to host, e.g. "/v1/models"


# Ordered by likelihood of presence on a developer machine. Detection
# results preserve this order in the response so the renderer can default
# to the first detected runtime.
_RUNTIME_PROBES: list[_RuntimeProbe] = [
    _RuntimeProbe(
        name="Ollama",
        base_url="http://localhost:11434/v1",
        # Ollama exposes both `/api/tags` (native) and `/v1/models`
        # (OpenAI-compat, added in 0.1.24 / Feb 2024). We use the
        # OpenAI-compat path so the parsing code is shared with LM Studio
        # — same response shape (`{data: [{id, ...}]}`).
        models_path="/v1/models",
    ),
    _RuntimeProbe(
        name="LM Studio",
        base_url="http://localhost:1234/v1",
        models_path="/v1/models",
    ),
    _RuntimeProbe(
        name="llama.cpp server",
        # llama.cpp's example server binds to 8080 and exposes OpenAI-compat
        # endpoints. Less ubiquitous than Ollama / LM Studio but still a
        # common target.
        base_url="http://localhost:8080/v1",
        models_path="/v1/models",
    ),
]


async def detect_runtimes() -> list[DetectedRuntime]:
    """Probe all known local runtimes in parallel; return only the ones
    that responded with a valid model list.

    Empty list is a normal, expected response (user has no local runtime
    running). Callers should NOT treat that as an error.
    """
    results = await asyncio.gather(
        *(_probe_one(p) for p in _RUNTIME_PROBES),
        return_exceptions=False,
    )
    return [r for r in results if r is not None]


async def _probe_one(probe: _RuntimeProbe) -> Optional[DetectedRuntime]:
    """Return DetectedRuntime if the probe target responds with a model
    list, else None.

    Any failure — connection refused, DNS, timeout, non-200, malformed
    JSON, no models — collapses to None. Detection is best-effort.
    """
    # httpx is already a transitive dep via the OpenAI/Anthropic SDKs and
    # the engine's existing Codex adapter. Import lazily so importing this
    # module is cheap (the engine startup path imports it).
    import httpx

    url = probe.base_url.rstrip("/").removesuffix("/v1") + probe.models_path
    try:
        async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT_S) as client:
            resp = await client.get(url)
    except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout):
        return None
    except Exception:  # noqa: BLE001 — anything else is also "not detected"
        return None

    if resp.status_code != 200:
        return None

    try:
        body = resp.json()
    except Exception:  # noqa: BLE001
        return None

    models = _extract_models(body)
    if not models:
        return None

    return DetectedRuntime(
        runtime=probe.name,
        base_url=probe.base_url,
        models=models,
    )


def _extract_models(body: object) -> list[str]:
    """Parse model id list from an OpenAI-compatible /v1/models response.

    Standard shape: `{"object": "list", "data": [{"id": "...", ...}, ...]}`.
    Both Ollama (>=0.1.24) and LM Studio return this shape. We accept
    whatever ordering the runtime returned — Ollama tends to list the
    most-recently-pulled model first; LM Studio lists what's currently
    loaded.
    """
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for entry in data:
        if isinstance(entry, dict):
            mid = entry.get("id")
            if isinstance(mid, str) and mid:
                out.append(mid)
    return out


def runtime_to_dict(r: DetectedRuntime) -> dict:
    """Serialize a DetectedRuntime for JSON-over-the-wire to the renderer."""
    return {
        "runtime": r.runtime,
        "base_url": r.base_url,
        "models": list(r.models),
    }
