"""Pricing resolver ported from the Lite app (engine/llm_providers.py).

Ported from Lite's test_provider_models.py ("Price resolution") and
test_thinking_allowance.py (the pure reasoning predicates). The safety
property: no per-token model ever prices at $0, so nothing walks past a
Cost Guard cap. OAuth and local stay $0.
"""

from __future__ import annotations

import pytest

from engine import llm_providers
from engine.cost_guard import worst_case_reservation
from engine.llm_providers import (
    anthropic_thinks_by_default,
    estimate_cost,
    gemini_thinks_by_default,
    infer_provider,
    normalize_model_id,
    openai_is_reasoning_model,
    openrouter_is_reasoning_model,
    per_token_rates,
    rates_for,
)


@pytest.fixture(autouse=True)
def _clean_runtime_maps():
    llm_providers._RUNTIME_RATES.clear()
    llm_providers._RUNTIME_REASONING.clear()
    yield
    llm_providers._RUNTIME_RATES.clear()
    llm_providers._RUNTIME_REASONING.clear()


def test_normalize_strips_8_digit_date_and_latest_only():
    assert normalize_model_id("claude-haiku-4-5-20251001") == "claude-haiku-4-5"
    assert normalize_model_id("claude-sonnet-4-6-latest") == "claude-sonnet-4-6"
    # OpenAI-style dates are NOT stripped (older snapshots can cost more).
    assert normalize_model_id("gpt-4o-2024-05-13") == "gpt-4o-2024-05-13"


def test_dated_anthropic_id_resolves_to_alias_row():
    assert rates_for("claude-haiku-4-5-20251001") == llm_providers._COST_PER_M_TOKENS["claude-haiku-4-5"]
    assert rates_for("claude-sonnet-4-6-latest") == llm_providers._COST_PER_M_TOKENS["claude-sonnet-4-6"]


def test_refreshed_rows_present():
    for model in ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5",
                  "claude-fable-5-2", "claude-mythos-5-2", "claude-opus-4-8"):
        assert model in llm_providers._COST_PER_M_TOKENS, model


@pytest.mark.parametrize("model,expected", [
    ("claude-mythos-1", (15.0, 75.0)),
    ("claude-opus-9", (15.0, 75.0)),
    ("claude-fable-6", (15.0, 75.0)),
    ("claude-sonnet-9", (5.0, 25.0)),
    ("claude-haiku-9", (5.0, 25.0)),
    ("gpt-7-nova", (15.0, 60.0)),
    ("o5-mini", (15.0, 60.0)),
    ("gemini-9-pro", (5.0, 20.0)),
    ("grok-9", (5.0, 15.0)),
    ("anthropic/claude-opus-9.1", (15.0, 75.0)),
    ("openai/gpt-7", (15.0, 60.0)),
    ("google/gemini-9", (5.0, 20.0)),
    ("x-ai/grok-9", (5.0, 15.0)),
    ("mystery-vendor/model", (15.0, 75.0)),
])
def test_unknown_models_get_family_ceilings(model, expected):
    r = rates_for(model)
    assert (r["input"], r["output"]) == expected


def test_openrouter_ids_reuse_first_party_rows_before_ceilings():
    assert rates_for("openai/gpt-4o-mini") == llm_providers._COST_PER_M_TOKENS["gpt-4o-mini"]
    # OpenRouter writes Claude versions with dots.
    assert rates_for("anthropic/claude-sonnet-4.6") == llm_providers._COST_PER_M_TOKENS["claude-sonnet-4-6"]
    assert rates_for("anthropic/claude-haiku-5.5") == llm_providers._COST_PER_M_TOKENS["claude-haiku-5-5"]


def test_legacy_gpt4_is_not_under_reserved():
    for mid in ("gpt-4", "gpt-4-0613", "gpt-4-32k", "openai/gpt-4"):
        r = rates_for(mid)
        assert r["input"] >= 30.0 and r["output"] >= 60.0, mid


@pytest.mark.parametrize("model", [
    "gpt-5-pro", "gpt-5.5-pro", "o1-pro", "o3-pro", "o3-deep-research", "gpt-4.5-preview",
    "openai/gpt-5.5-pro", "openai/o1-pro",
])
def test_premium_openai_tiers_get_the_premium_ceiling(model):
    r = rates_for(model)
    assert r["input"] >= 150.0 and r["output"] >= 600.0, model


def test_gemini_pro_is_not_treated_as_an_openai_premium_tier():
    assert rates_for("gemini-9-pro") == {"input": 5.0, "output": 20.0}


def test_runtime_price_beats_first_party_mapping():
    llm_providers.register_runtime_rates("openai/gpt-4o-mini", input_per_m=0.2, output_per_m=0.8)
    assert rates_for("openai/gpt-4o-mini") == {"input": 0.2, "output": 0.8}


def test_estimate_cost_local_zero_cloud_ceiling():
    assert estimate_cost("llama3.2:latest", 10_000, 1_000, provider="local") == 0.0
    assert estimate_cost("MiniMax-M9", 1_000_000, 0, provider="minimax") == pytest.approx(15.0)
    # No provider and nothing matches: historical $0 (callers that cannot say).
    assert estimate_cost("llama3.2:latest", 10_000, 1_000) == 0.0
    # Old positional call shape still works for existing callers.
    assert estimate_cost("gpt-4o-mini", 1_000_000, 0) == pytest.approx(0.15)


def test_per_token_rates_is_never_none_or_zero():
    for model in ("deepseek-v9", "qwen3-max", "totally-unknown", "llama3.2:latest"):
        r = per_token_rates(model)
        assert r["input"] > 0 and r["output"] > 0, model
    assert per_token_rates("deepseek-v9") == llm_providers._CEIL_UNKNOWN
    assert per_token_rates("claude-sonnet-4-6", "anthropic") == llm_providers._COST_PER_M_TOKENS["claude-sonnet-4-6"]


def test_unknown_api_key_model_reserves_non_zero():
    for model in ("claude-brand-new-model", "gpt-7", "totally-unknown", "vendor/unknown"):
        assert worst_case_reservation(model=model, auth_kind="api_key", max_tokens=400) > 0.0, model


def test_oauth_and_local_still_reserve_zero():
    for model in ("claude-brand-new-model", "gpt-7", "llama3.2:latest", "vendor/unknown"):
        assert worst_case_reservation(model=model, auth_kind="oauth", max_tokens=400) == 0.0
        assert worst_case_reservation(model=model, auth_kind="local", max_tokens=400) == 0.0


@pytest.mark.parametrize("model,provider", [
    ("anthropic/claude-opus-5.5", "openrouter"), ("claude-opus-5-5", "anthropic"),
    ("gpt-5", "openai"), ("o3", "openai"), ("gemini-2.5-pro", "gemini"),
    ("grok-4.3", "xai"), ("MiniMax-M2.7", None), ("llama3.2:latest", None),
])
def test_infer_provider(model, provider):
    assert infer_provider(model) == provider


@pytest.mark.parametrize("model,expected", [
    ("claude-opus-5", True), ("claude-sonnet-5-5", True), ("claude-haiku-5-5", True),
    ("claude-fable-5-2", True), ("claude-mythos-5-1", True),
    ("claude-sonnet-5-5-20261001", True),
    ("claude-opus-4-8", False), ("claude-sonnet-4-6", False), ("claude-haiku-4-5-20251001", False),
])
def test_anthropic_thinks_by_default(model, expected):
    assert anthropic_thinks_by_default(model) is expected


@pytest.mark.parametrize("model,expected", [
    ("gemini-2.5-flash", True), ("gemini-2.5-pro", True), ("gemini-3.1-flash-lite", True),
    ("gemini-2.0-flash", False), ("gemini-2.5-flash-lite", False), ("gemini-flash-latest", True),
])
def test_gemini_thinks_by_default(model, expected):
    assert gemini_thinks_by_default(model) is expected


@pytest.mark.parametrize("model,expected", [
    ("gpt-5", True), ("gpt-5-mini", True), ("o4-mini", True), ("gpt-5-pro", True),
    ("gpt-5.1", False), ("gpt-5.5", False), ("gpt-4o-mini", False), ("gpt-5-chat-latest", False),
])
def test_openai_is_reasoning_model_lite_semantics(model, expected):
    # Lite semantics (effort "none" for gpt-5.1+). Pro's estimator layers its
    # own rule on top: see cost_guard.pro_model_reasons.
    assert openai_is_reasoning_model(model) is expected


def test_openrouter_catalog_flag_wins_except_for_openai():
    llm_providers.register_runtime_reasoning("qwen/qwen3.8-2.4t-a95b", capable=True)
    assert openrouter_is_reasoning_model("qwen/qwen3.8-2.4t-a95b")
    llm_providers.register_runtime_reasoning("anthropic/claude-opus-5.5", capable=False)
    assert not openrouter_is_reasoning_model("anthropic/claude-opus-5.5")
    llm_providers.register_runtime_reasoning("openai/gpt-5-mini", capable=False)
    assert openrouter_is_reasoning_model("openai/gpt-5-mini")
