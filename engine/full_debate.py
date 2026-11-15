"""Full-graph debate adapter for Trading Agents Lab Pro.

Where the free app's ``engine/live_debate.py`` runs a deliberately simplified,
single-pass reimplementation of the analysis, the Pro app runs the REAL upstream
``tradingagents`` LangGraph graph: tool-using analysts, multi-round bull/bear and
risk debates, a deep/quick model split, and cross-run memory. This module is the
adapter that drives that graph and streams progress to the SAME desktop
WebSocket UI the free app already speaks to.

Design notes (the non-obvious parts, proven by probes in the P1 review gate):

* The desktop WS handler is async and the graph's node functions are synchronous
  blocking calls that each take seconds. We therefore drive the graph with
  ``graph.astream`` (LangGraph runs the sync nodes on a worker-thread executor,
  so the event loop stays free) and expose this adapter as an ``async`` generator
  that ``server.py`` can iterate with a uniform ``async for``.

* We stream with ``stream_mode=["updates", "values"]``. The ``updates`` chunks
  give us per-node deltas (for progress + round tracking); the ``values`` chunks
  give us the full accumulated state, the last of which we keep as the final
  state that feeds decision parsing and the memory hooks. This avoids fragile
  manual merging of update deltas.

* A token cap is enforced by a LangChain callback that raises when the running
  total crosses the cap. LangChain swallows callback exceptions by default, so
  the handler sets ``raise_error = True`` to make the raise propagate out of the
  stream and halt the graph. Because ``on_llm_end`` fires AFTER the offending
  call, the cap is a "may slightly exceed" safety backstop, not a hard ceiling;
  the primary budget control remains the pre-flight cost-guard reservation.

* The same meter enforces a USD limit (Cost Guard's mid-run stop; the limit is
  computed at reserve time, see ``cost_guard._run_limit``). Running usage is
  priced exactly the way the finalized cost is (``_run_rates``), so the stop
  decision matches the ledger. To avoid overshooting by a whole call, the check
  runs BEFORE each LLM call: if spent-so-far plus the largest single call seen
  so far could cross the limit, the call is refused and the graph halts with a
  ``run.cost_cap`` event. A run whose remaining calls are all small enough
  finishes normally even if it overshoots its own estimate.

* The real Portfolio Manager emits a 5-tier rating (Buy / Overweight / Hold /
  Underweight / Sell) with no confidence field, rendered as markdown. The free
  app's STANCE=/CONVICTION= regex parser does not match that shape, so we parse
  the PM markdown here and map the rating 1:1 onto the analytical stance
  vocabulary (engine/stance.py) while also surfacing the richer native fields.
  A post-run quick-model call scores the bull/bear thesis strengths + risk
  level; the app's own surfaces never carry the raw trade-directive rating.
"""

from __future__ import annotations

import asyncio
import math
import os
import re
import sys
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph


# ---------------------------------------------------------------------------
# Node -> wire vocabulary mapping
#
# The desktop UI groups the pipeline into four phases with these exact strings:
# "analysts", "researchers", "trader", "risk". The real graph's node keys differ
# from the free app's agent names, so we translate explicitly. Note that several
# risk-phase nodes ALSO end in " Analyst", so we cannot infer phase from a
# suffix; the mapping is exhaustive and by exact node name.
# ---------------------------------------------------------------------------

# Analyst nodes: real graph key -> (wire agent name, wire phase).
_ANALYST_NODES: Dict[str, str] = {
    "Market Analyst": "technical_analyst",
    # Upstream renamed this graph node "Social Analyst" -> "Sentiment Analyst"
    # (v0.4.x). The state field (sentiment_report) and our wire name were already
    # aligned; only the node label lagged. Key on the current label.
    "Sentiment Analyst": "sentiment_analyst",
    "News Analyst": "news_analyst",
    "Fundamentals Analyst": "fundamental_analyst",
}

# Researcher / manager debate loop (bull <-> bear until the research manager).
_RESEARCH_NODES: Dict[str, str] = {
    "Bull Researcher": "bull_researcher",
    "Bear Researcher": "bear_researcher",
    "Research Manager": "research_manager",
}

_TRADER_NODES: Dict[str, str] = {"Trader": "trader"}

# Risk debate loop (aggressive -> conservative -> neutral until the PM).
_RISK_NODES: Dict[str, str] = {
    "Aggressive Analyst": "risk_aggressive",
    "Conservative Analyst": "risk_conservative",
    "Neutral Analyst": "risk_neutral",
    "Portfolio Manager": "portfolio_manager",
}

# Which risk_debate_state field holds THIS node's own line. The state keeps
# one field per speaker (all persist across turns), so transcript extraction
# must select by speaker — see _extract_content.
_RISK_NODE_RESPONSE_KEY: Dict[str, str] = {
    "Aggressive Analyst": "current_aggressive_response",
    "Conservative Analyst": "current_conservative_response",
    "Neutral Analyst": "current_neutral_response",
}

_PHASE_OF: Dict[str, str] = {}
for _n in _ANALYST_NODES:
    _PHASE_OF[_n] = "analysts"
for _n in _RESEARCH_NODES:
    _PHASE_OF[_n] = "researchers"
for _n in _TRADER_NODES:
    _PHASE_OF[_n] = "trader"
for _n in _RISK_NODES:
    _PHASE_OF[_n] = "risk"

_AGENT_OF: Dict[str, str] = {
    **_ANALYST_NODES,
    **_RESEARCH_NODES,
    **_TRADER_NODES,
    **_RISK_NODES,
}

# Analyst tool nodes -> wire agent name. Upstream keeps the tool node's key as
# "social" even though the agent node was renamed "Social Analyst" ->
# "Sentiment Analyst" (v0.4.x), so the tool-node label can no longer be derived
# from the agent label by string munging. Map explicitly by exact tool-node name.
_TOOL_NODE_AGENT: Dict[str, str] = {
    "tools_market": "technical_analyst",
    "tools_social": "sentiment_analyst",
    "tools_news": "news_analyst",
    "tools_fundamentals": "fundamental_analyst",
}

# Graph node names are the contract between the upstream library and this
# adapter. If an upstream refresh renames a node (as v0.4.x did:
# "Social Analyst" -> "Sentiment Analyst"), the old key silently maps to
# nothing and the node's activity vanishes from the wire. Warn once per unknown
# node so that class of drift is loud in the engine log instead of invisible.
_WARNED_UNMAPPED_NODES: set = set()

# The upstream Portfolio Manager emits a native 5-tier rating
# (Buy/Overweight/Hold/Underweight/Sell). The app deliberately does not
# surface trade directives, so the rating maps 1:1 onto the analytical
# stance vocabulary (engine/stance.py) at this presentation layer. The
# pristine upstream library is untouched; only what we SAY about its
# output changes. Conviction keeps the documented heuristic.
_RATING_TO_STANCE = {
    "buy": "bullish",
    "overweight": "moderately_bullish",
    "hold": "neutral",
    "underweight": "moderately_bearish",
    "sell": "bearish",
}
_RATING_TO_CONVICTION = {
    "buy": 0.85,
    "overweight": 0.65,
    "hold": 0.5,
    "underweight": 0.65,
    "sell": 0.85,
}

# Provider -> the environment variable the upstream library's LLM client reads
# the API key from at construction time. The library does NOT thread an explicit
# key from config (its `_get_provider_kwargs` only builds effort/thinking kwargs),
# so a BYO key must reach the client via its standard env var. Names mirror the
# clients under `tradingagents/llm_clients/`; keep this in sync if that grows.
_PROVIDER_ENV_VAR: Dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "glm": "ZHIPU_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    # ollama / other local runtimes need no key (client sends a dummy "ollama").
}


class TokenCapExceeded(Exception):
    """Raised by the in-run token meter when the running total crosses the cap."""


class CostCapExceeded(Exception):
    """Raised by the in-run meter when the next call could cross the USD limit."""


# Messages shown to the user when the USD stop fires. No em or en dashes:
# these strings reach the analysis screen.
_COST_CAP_MESSAGE = (
    "Stopped: this run reached your Cost Guard {dimension} cap after spending "
    "${used:.2f}. Raise the cap in Settings, Cost Guard, or use Override."
)
_RUNAWAY_MESSAGE = (
    "Stopped: this run spent ${used:.2f}, about three times its estimate of "
    "${est:.2f}, so Cost Guard ended it as a likely runaway. Check the models "
    "and round counts in Settings, then try again."
)


def _price(rates: Optional[Dict[str, float]], in_tok: int, out_tok: int) -> float:
    """USD for a token count at per-1M rates. No rates (OAuth/local) is $0."""
    if not rates:
        return 0.0
    return (in_tok * rates["input"] + out_tok * rates["output"]) / 1_000_000


class _TokenMeter(BaseCallbackHandler):
    """Meter token usage across the whole graph run and abort when over a cap.

    Two independent stops: the optional token cap (checked after each call)
    and the optional USD limit (checked before each call, see the module
    docstring). ``raise_error = True`` is mandatory: without it LangChain logs
    and swallows exceptions raised inside callbacks, so neither stop would
    actually halt the run. With it, the raise propagates out of
    ``graph.astream`` and halts.
    """

    raise_error = True

    def __init__(
        self,
        cap: Optional[int],
        *,
        rates: Optional[Dict[str, float]] = None,
        usd_limit: Optional[float] = None,
        rate_for: Optional[Callable[[str], Optional[Dict[str, float]]]] = None,
    ) -> None:
        self.cap = cap
        # Fallback rates (the higher of deep and quick) for a call whose model
        # the callback could not identify. None means the run is free.
        self.rates = rates
        # Per-model resolver: a split run (e.g. Opus deep, Haiku quick) is
        # billed per call at that call's own model, not at the pricier one.
        self.rate_for = rate_for
        # A USD limit only means something when calls are priced.
        self.usd_limit = usd_limit if rates else None
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0
        self.max_call_usd = 0.0
        # Running USD total, summed call by call. This is THE cost: the
        # mid-run stop, cost.usage, session.complete and the finalized
        # reservation all read it, so they always agree.
        self._spent_usd = 0.0
        # LangChain run_id -> model name, captured at call start.
        self._call_models: Dict[Any, str] = {}
        # Set whenever the USD stop fires. Upstream agents sometimes catch
        # exceptions around an LLM call (e.g. a structured-output fallback),
        # which could swallow the raise; full_debate checks this flag after
        # the graph so a swallowed stop still ends the run as run.cost_cap.
        self.tripped = False

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def spent_usd(self) -> float:
        return self._spent_usd

    def _rates_for_call(self, run_id: Any, response: Any = None) -> Optional[Dict[str, float]]:
        """Rates for one finished call: its own model when known, else the
        conservative fallback. Free runs (no fallback rates) stay $0."""
        if not self.rates:
            return None
        model = self._call_models.pop(run_id, None) if run_id is not None else None
        if not model and response is not None:
            try:
                llm_output = getattr(response, "llm_output", None) or {}
                model = llm_output.get("model_name") or llm_output.get("model")
            except Exception:
                model = None
        if model and self.rate_for is not None:
            try:
                rates = self.rate_for(str(model))
                if rates:
                    return rates
            except Exception:
                pass
        return self.rates

    def _remember_model(self, kwargs: Dict[str, Any]) -> None:
        run_id = kwargs.get("run_id")
        if run_id is None:
            return
        params = kwargs.get("invocation_params") or {}
        meta = kwargs.get("metadata") or {}
        model = (
            params.get("model")
            or params.get("model_name")
            or params.get("model_id")
            or meta.get("ls_model_name")
        )
        if model:
            self._call_models[run_id] = str(model)

    def next_call_could_exceed(self) -> bool:
        """True when one more call as large as the largest so far could push
        spend past the USD limit. The first call is always allowed (nothing
        to size it by); the after-call check in on_llm_end catches a call
        that by itself carries spend over the limit."""
        if self.usd_limit is None:
            return False
        return self.spent_usd + self.max_call_usd > self.usd_limit

    def _check_before_call(self) -> None:
        if self.next_call_could_exceed():
            self.tripped = True
            raise CostCapExceeded(
                f"USD limit {self.usd_limit:.4f} would be exceeded "
                f"(spent {self.spent_usd:.4f}, largest call {self.max_call_usd:.4f})"
            )

    # Chat models fire on_chat_model_start; plain LLMs fire on_llm_start.
    def on_chat_model_start(self, serialized: Any, messages: Any, **kwargs: Any) -> None:
        self._remember_model(kwargs)
        self._check_before_call()

    def on_llm_start(self, serialized: Any, prompts: Any, **kwargs: Any) -> None:
        self._remember_model(kwargs)
        self._check_before_call()

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        self.calls += 1
        in_tok = out_tok = 0
        # langchain_anthropic / openai surface usage in a couple of shapes.
        try:
            llm_output = getattr(response, "llm_output", None) or {}
            usage = llm_output.get("usage", {}) if isinstance(llm_output, dict) else {}
            in_tok = usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0)
            out_tok = usage.get("output_tokens", 0) or usage.get("completion_tokens", 0)
        except Exception:
            pass
        if not (in_tok or out_tok):
            try:
                for gen_list in response.generations:
                    for gen in gen_list:
                        um = getattr(gen.message, "usage_metadata", None) or {}
                        in_tok += um.get("input_tokens", 0)
                        out_tok += um.get("output_tokens", 0)
            except Exception:
                pass
        self.input_tokens += in_tok
        self.output_tokens += out_tok
        call_usd = _price(self._rates_for_call(kwargs.get("run_id"), response), in_tok, out_tok)
        self._spent_usd += call_usd
        self.max_call_usd = max(self.max_call_usd, call_usd)
        if self.cap is not None and self.total >= self.cap:
            raise TokenCapExceeded(f"token cap {self.cap} exceeded ({self.total})")
        if self.usd_limit is not None and self.spent_usd > self.usd_limit:
            self.tripped = True
            raise CostCapExceeded(
                f"USD limit {self.usd_limit:.4f} exceeded ({self.spent_usd:.4f})"
            )


def _last_message_has_tool_calls(delta: Dict[str, Any]) -> bool:
    """True when the analyst's latest message is a request to call tools.

    An analyst node re-emits on every iteration of its tool loop. It has produced
    its final report only on the pass whose last message carries NO tool calls;
    that is the pass we surface as an ``agent.message``. The earlier passes are
    surfaced as lightweight ``agent.activity`` so the UI can show a "using tools"
    indicator instead of a silent gap.
    """
    msgs = delta.get("messages") or []
    if not msgs:
        return False
    last = msgs[-1]
    return bool(getattr(last, "tool_calls", None))


def _round_from_delta(delta: Dict[str, Any], phase: str) -> Optional[int]:
    """Derive the debate round from the state counter carried in the delta.

    The two debate loops count turns differently: the bull/bear loop runs two
    turns per round (``count >= 2 * max_debate_rounds``) and the risk loop runs
    three (``count >= 3 * max_risk_discuss_rounds``). The PM freezes the risk
    counter, so it inherits the last risk round.
    """
    if phase == "researchers":
        state = delta.get("investment_debate_state") or {}
        count = state.get("count")
        if isinstance(count, int) and count > 0:
            return math.ceil(count / 2)
    elif phase == "risk":
        state = delta.get("risk_debate_state") or {}
        count = state.get("count")
        if isinstance(count, int) and count > 0:
            return math.ceil(count / 3)
    return None


def _parse_pm_decision(final_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Parse the Portfolio Manager markdown into the wire assessment contract.

    Maps the native 5-tier rating onto the analytical stance vocabulary and a
    heuristic ``conviction``. The upstream rating word itself (a trade
    directive) is deliberately NOT passed through: the app's own surfaces
    never issue buy/sell/hold. The PM's raw markdown still appears verbatim
    in the transcript as the agent's own speech.
    """
    text = ""
    if final_state:
        text = final_state.get("final_trade_decision") or ""

    rating_match = re.search(r"\*\*Rating\*\*:\s*([A-Za-z]+)", text)
    rating = rating_match.group(1).strip() if rating_match else ""
    rating_key = rating.lower()

    stance = _RATING_TO_STANCE.get(rating_key, "neutral")
    conviction = _RATING_TO_CONVICTION.get(rating_key, 0.5)

    summary_match = re.search(
        r"\*\*Executive Summary\*\*:\s*(.+?)(?:\n\*\*|\Z)", text, re.DOTALL
    )
    thesis_match = re.search(
        r"\*\*Investment Thesis\*\*:\s*(.+?)(?:\n\*\*|\Z)", text, re.DOTALL
    )
    reasoning = (summary_match.group(1).strip() if summary_match else "").strip()
    if not reasoning:
        reasoning = text.strip() or "No assessment text produced."

    price_match = re.search(r"\*\*Price Target\*\*:\s*([\d.]+)", text)
    horizon_match = re.search(r"\*\*Time Horizon\*\*:\s*(.+?)(?:\n|\Z)", text)

    return {
        "stance": stance,
        "conviction": conviction,
        "reasoning": reasoning,
        # Pro-richer native fields. price_target is displayed as the
        # "modeled scenario range" in the UI (an analytical estimate, not
        # a directive); the field name stays for wire stability.
        "investment_thesis": (thesis_match.group(1).strip() if thesis_match else None),
        "price_target": (float(price_match.group(1)) if price_match else None),
        "time_horizon": (horizon_match.group(1).strip() if horizon_match else None),
    }


_STRENGTH_PROMPT = """You are scoring a finished research debate for an educational analysis tool.

Bull researcher's case:
{bull}

Bear researcher's case:
{bear}

Risk committee discussion:
{risk}

Score how strongly each side argued (evidence quality, specificity, internal
consistency), independently of which side you agree with, and rate the overall
risk profile the committee surfaced. Output exactly three lines:
BULL_STRENGTH=<integer 0-100>
BEAR_STRENGTH=<integer 0-100>
RISK=LOW | RISK=MODERATE | RISK=ELEVATED
"""


def _clip(text: str, n: int = 4000) -> str:
    return text if len(text) <= n else text[:n] + " …[truncated]"


def _score_thesis_strengths(graph: Any, final_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """One quick-model call scoring the bull/bear cases and risk level.

    Uses ``graph.quick_thinking_llm`` (already constructed with the run's
    BYO key AND the CostGuard token meter callbacks, so the extra call is
    metered like every other). Runs synchronously — call via
    ``asyncio.to_thread``. Any failure degrades to null strengths, which
    the UI renders by hiding the strength bars; never fails the run.
    """
    empty = {"bull_strength": None, "bear_strength": None, "risk_level": None}
    if not final_state:
        return empty
    inv = final_state.get("investment_debate_state") or {}
    risk = final_state.get("risk_debate_state") or {}
    bull = str(inv.get("bull_history") or "").strip()
    bear = str(inv.get("bear_history") or "").strip()
    risk_text = str(risk.get("history") or "").strip()
    if not bull or not bear:
        return empty
    try:
        prompt = _STRENGTH_PROMPT.format(
            bull=_clip(bull), bear=_clip(bear), risk=_clip(risk_text) or "(none)"
        )
        response = graph.quick_thinking_llm.invoke(prompt)
        content = str(getattr(response, "content", response))
        out: Dict[str, Any] = dict(empty)
        for key, field in (("BULL_STRENGTH", "bull_strength"), ("BEAR_STRENGTH", "bear_strength")):
            m = re.search(rf"{key}\s*=\s*([0-9]+)", content, re.IGNORECASE)
            if m:
                v = int(m.group(1))
                if 0 <= v <= 100:
                    out[field] = v
        m = re.search(r"RISK\s*=\s*(LOW|MODERATE|ELEVATED)", content, re.IGNORECASE)
        if m:
            out["risk_level"] = m.group(1).lower()
        return out
    except Exception:
        return empty


def _build_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge caller config over the library defaults, failing loud on the essentials.

    A missing provider/model key would otherwise silently fall back to the
    library default, which for a paid product is a confusing wrong-model bug
    rather than an error.
    """
    merged = dict(DEFAULT_CONFIG)
    if config:
        merged.update(config)
    missing = [k for k in ("llm_provider", "deep_think_llm", "quick_think_llm") if not merged.get(k)]
    if missing:
        raise ValueError(f"full_debate config missing required keys: {missing}")
    return merged


def _run_rates(auth_kind: str, merged: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Fallback per-1M rates for THIS run: the higher of deep and quick.

    The meter prices each call at its own model (``_run_rate_for``); these
    rates are used only for a call whose model the callback could not
    identify, and to size the per-call overshoot guard before any call has
    run. Conservative on purpose. Unknown models resolve to a family ceiling
    via ``per_token_rates``, never $0. OAuth (subscription) and local runs
    return None ($0).

    ``per_token_rates`` is imported lazily so a test that loads this module
    without package context never trips the relative import; it then gets
    None ($0), which such tests do not assert on.
    """
    if auth_kind in ("oauth", "local"):
        return None
    try:
        from .llm_providers import per_token_rates

        provider = (merged.get("llm_provider") or "").lower() or None
        deep = per_token_rates(merged.get("deep_think_llm") or "", provider)
        quick = per_token_rates(merged.get("quick_think_llm") or "", provider)
        return {
            "input": max(deep["input"], quick["input"]),
            "output": max(deep["output"], quick["output"]),
        }
    except Exception:  # noqa: BLE001 — pricing is best-effort, never fatal
        return None


def _run_rate_for(auth_kind: str, merged: Dict[str, Any]):
    """Per-model rate resolver for the meter, or None for a free run."""
    if auth_kind in ("oauth", "local"):
        return None
    try:
        from .llm_providers import per_token_rates
    except Exception:  # noqa: BLE001
        return None
    provider = (merged.get("llm_provider") or "").lower() or None
    return lambda model: per_token_rates(model, provider)


def _run_cost(auth_kind: str, merged: Dict[str, Any], meter: "_TokenMeter") -> float:
    """USD for the metered run: the meter's call-by-call total, the same
    number its mid-run stop acts on. OAuth/local runs are always $0."""
    if auth_kind in ("oauth", "local"):
        return 0.0
    return meter.spent_usd


def _finalize_reservation(
    reservation_id: Optional[str],
    auth_kind: str,
    merged: Dict[str, Any],
    meter: "_TokenMeter",
    *,
    completed: bool,
) -> None:
    """Settle the pre-flight CostGuard reservation with the metered cost.

    Runs on any exit path (normal completion, token-cap or cost-cap abort,
    node error, or client disconnect), bills the real partial cost so a
    mid-run exit does not leave the reservation stuck as in-flight, and is
    best-effort (a finalize failure must never break the stream).

    ``completed`` is False for every exit that did not yield session.complete.
    Those runs write no sessions row, so the reservation is finalized as
    ``unrecorded`` and its real cost counts toward the caps on its own;
    otherwise an aborted run would be free against every cap. Imported lazily
    so headless tests that never reserve don't touch cost_guard.
    """
    if not reservation_id:
        return
    try:
        from . import cost_guard as _cost_guard

        _cost_guard.finalize_reservation(
            reservation_id,
            actual_cost_usd=_run_cost(auth_kind, merged, meter),
            unrecorded=not completed,
        )
    except Exception as exc:  # noqa: BLE001 — finalize is best-effort
        sys.stderr.write(
            f"[full_debate] cost_guard finalize failed: "
            f"{type(exc).__name__}: {exc}\n"
        )


async def full_debate(
    ticker: str,
    trade_date: str,
    *,
    config: Optional[Dict[str, Any]] = None,
    selected_analysts: Optional[List[str]] = None,
    token_cap: Optional[int] = None,
    past_context: str = "",
    api_key: Optional[str] = None,
    auth_kind: str = "api_key",
    oauth_account_id: Optional[str] = None,
    reservation_id: Optional[str] = None,
    alpha_vantage_key: Optional[str] = None,
    usd_limit: Optional[float] = None,
    usd_limit_reason: Optional[str] = None,
    usd_limit_dimension: Optional[str] = None,
    est_cost_usd: Optional[float] = None,
) -> AsyncIterator[Dict[str, Any]]:
    """Drive the full LangGraph diligence graph, yielding UI-compatible events.

    Event stream (extends the free app's contract):
      session.start, graph.plan, phase.transition, agent.activity, agent.message,
      cost.usage, run.token_cap / run.cost_cap (on abort), run.error (on
      failure), session.complete.

    ``api_key`` is the BYO provider key; when present it is injected into the
    provider's standard env var only for the synchronous graph-construction span
    (see below). On the OAuth path (``auth_kind == "oauth"``) it instead carries
    the OAuth ACCESS TOKEN and, together with ``oauth_account_id``, routes
    OpenAI LLM construction through the Codex subscription backend via
    ``codex_llm.codex_factory_patch`` — same synchronous window, different
    injection. ``reservation_id`` ties this run to a pre-flight CostGuard
    reservation that is finalized on exit (any exit path) with the metered cost;
    pass ``None`` (the default) to run without CostGuard, as the headless tests do.

    ``usd_limit`` (with its ``usd_limit_reason`` "cap" or "runaway", the cap
    ``usd_limit_dimension``, and the reservation's ``est_cost_usd``) is the
    mid-run USD stop server.py reads from the reservation; None disables it.
    """
    analysts = selected_analysts or ["market", "social", "news", "fundamentals"]
    meter = _TokenMeter(token_cap)
    merged: Dict[str, Any] = {}
    final_state: Optional[Dict[str, Any]] = None
    last_phase: Optional[str] = None
    aborted = False
    # Set just before session.complete is yielded; any other exit leaves it
    # False so the reservation is finalized as an unrecorded (aborted) cost.
    completed = False
    free = auth_kind in ("oauth", "local")

    def _refresh_limit() -> None:
        """After each node: tell Cost Guard what this run has really used and
        pick up the current cap headroom (another run may have started or
        finished meanwhile). See cost_guard.refresh_run_limit."""
        if not reservation_id or meter.usd_limit is None:
            return
        try:
            from . import cost_guard as _cg

            fresh = _cg.refresh_run_limit(
                reservation_id,
                spent_usd=meter.spent_usd,
                next_call_usd=meter.max_call_usd,
            )
        except Exception:  # noqa: BLE001 — never fail the run over a refresh
            return
        # Only ever tighten: if another run used room since our reserve, we
        # get less; if room freed up, we keep the limit we started with
        # (simple and conservative, the run was sized for that limit).
        if fresh is not None and meter.usd_limit is not None:
            meter.usd_limit = min(meter.usd_limit, fresh)

    def _cost_event() -> Dict[str, Any]:
        _refresh_limit()
        return {
            "type": "cost.usage",
            "input_tokens": meter.input_tokens,
            "output_tokens": meter.output_tokens,
            # Running cost at the same rates the finalized ledger uses.
            "est_cost_usd": round(meter.spent_usd, 4),
            "free": free,
        }

    def _cost_cap_event() -> Dict[str, Any]:
        used = meter.spent_usd
        if usd_limit_reason == "cap":
            message = _COST_CAP_MESSAGE.format(
                dimension=usd_limit_dimension or "spending", used=used
            )
        else:
            message = _RUNAWAY_MESSAGE.format(used=used, est=float(est_cost_usd or 0.0))
        return {
            "type": "run.cost_cap",
            "used_usd": round(used, 4),
            "limit_usd": round(float(meter.usd_limit or 0.0), 4),
            "reason": usd_limit_reason or "runaway",
            "dimension": usd_limit_dimension,
            "input_tokens": meter.input_tokens,
            "output_tokens": meter.output_tokens,
            "message": message,
        }

    # Outer try/finally guarantees the CostGuard reservation is settled on EVERY
    # exit path: a config or construction failure before the first yield, a
    # token-cap abort, a node error, or a client disconnect (GeneratorExit thrown
    # at ANY yield, including the two early ones). `merged` starts empty so a
    # pre-config failure still finalizes cleanly (priced at zero: no LLM calls).
    try:
        merged = _build_config(config)
        # Price the meter now that the deep/quick models are known. Same rates
        # as _run_cost, so the mid-run stop agrees with the finalized cost.
        meter.rates = _run_rates(auth_kind, merged)
        meter.rate_for = _run_rate_for(auth_kind, merged)
        meter.usd_limit = usd_limit if meter.rates else None

        # Data-tool key (Alpha Vantage) must be in the environment for the WHOLE
        # run: the library's dataflows tools (news / social / fundamentals) read
        # it at tool-CALL time on the astream worker thread, mid-run, NOT at
        # construction, so the LLM-key construction-window trick does not apply.
        # The renderer is the source of truth (it sends the current key per run),
        # so we set it when present and CLEAR it when absent: that way a user who
        # removes their key in Settings actually stops using it, rather than a
        # stale key lingering in the process env. No finally-restore: the Pro
        # engine is a single-user sidecar and a batch shares one key config
        # (no mixed keyed/keyless concurrency to race). A market-only run never
        # reads the key, so clearing it there is harmless.
        if alpha_vantage_key and alpha_vantage_key.strip():
            os.environ["ALPHA_VANTAGE_API_KEY"] = alpha_vantage_key.strip()
        else:
            os.environ.pop("ALPHA_VANTAGE_API_KEY", None)

        # BYO-key injection. The upstream library's LLM clients capture the
        # provider API key from the standard env var at construction time and do
        # not accept an explicit key threaded from config. We set the env var
        # ONLY around the synchronous construction span and restore it before any
        # await/yield. Concurrency-safe: TradingAgentsGraph.__init__ and
        # create_initial_state are synchronous, so on the single asyncio loop no
        # other debate coroutine can interleave between set and restore (no await
        # point), and the built clients never re-read the env from worker threads.
        provider = (merged.get("llm_provider") or "").lower()
        # OAuth (ChatGPT subscription): don't touch the env var — the access
        # token is not an API key and must not leak into OPENAI_API_KEY where
        # an unrelated SDK path could pick it up. Instead patch the LLM
        # factory so provider="openai" builds Codex-backed clients. Same
        # synchronous construction window, enforced the same way.
        use_codex = (
            auth_kind == "oauth" and provider == "openai" and bool(api_key)
        )
        env_var = (
            _PROVIDER_ENV_VAR.get(provider) if (api_key and not use_codex) else None
        )
        _prev_env: Optional[str] = None
        if env_var and api_key:
            _prev_env = os.environ.get(env_var)
            os.environ[env_var] = api_key
        if use_codex:
            from .codex_llm import codex_factory_patch

            _codex_ctx = codex_factory_patch(api_key, oauth_account_id or "")
            _codex_ctx.__enter__()
        else:
            _codex_ctx = None
        try:
            # A fresh graph per session: TradingAgentsGraph holds mutable instance
            # state (self.ticker / self.curr_state), so it must not be shared.
            graph = TradingAgentsGraph(
                selected_analysts=analysts,
                debug=False,
                config=merged,
                callbacks=[meter],
            )
            # Replicate the library's memory retrieval. Its normal propagate()
            # seeds the initial state with prior same/cross-ticker decisions via
            # get_past_context so the graph can reflect on them; bypassing
            # _run_graph drops that, so we call it explicitly here (a caller-
            # supplied past_context still wins). Best-effort, and a local read, so
            # it stays inside the synchronous construction window.
            effective_past = past_context
            if not effective_past:
                try:
                    effective_past = graph.memory_log.get_past_context(ticker) or ""
                except Exception:  # noqa: BLE001 — memory is supplemental
                    effective_past = ""
            state = graph.propagator.create_initial_state(
                ticker, trade_date, past_context=effective_past
            )
        finally:
            # Restore BEFORE any await/yield so the mutation window stays sync.
            if _codex_ctx is not None:
                _codex_ctx.__exit__(None, None, None)
            if env_var and api_key:
                if _prev_env is None:
                    os.environ.pop(env_var, None)
                else:
                    os.environ[env_var] = _prev_env

        yield {"type": "session.start", "ticker": ticker, "trade_date": trade_date}
        # graph.plan lets the UI render honest totals for the deterministic
        # phases. Analyst per-phase counts are NOT included: their tool loops make
        # the count non-deterministic, so the UI tracks analysts by explicit
        # completion, not a fraction.
        yield {
            "type": "graph.plan",
            "analysts": analysts,
            "max_debate_rounds": int(merged.get("max_debate_rounds", 1)),
            "max_risk_rounds": int(merged.get("max_risk_discuss_rounds", 1)),
            "deep_model": merged.get("deep_think_llm"),
            "quick_model": merged.get("quick_think_llm"),
        }

        try:
            async for mode, chunk in graph.graph.astream(
                state,
                stream_mode=["updates", "values"],
                config={"recursion_limit": 100},
            ):
                if mode == "values":
                    final_state = chunk
                    continue

                # mode == "updates": chunk is {node_name: state_delta}
                for node, delta in (chunk or {}).items():
                    delta = delta or {}

                    if node.startswith("Msg Clear "):
                        continue  # internal message-buffer reset; no user meaning

                    if node.startswith("tools_"):
                        agent = _TOOL_NODE_AGENT.get(node)
                        yield {
                            "type": "agent.activity",
                            "agent": agent or node,
                            "node": node,
                            "status": "using_tools",
                        }
                        continue

                    phase = _PHASE_OF.get(node)
                    if phase is None:
                        # START/END and message-buffer resets are expected here;
                        # anything else is likely an upstream node rename we have
                        # not caught up to. Warn once so it is not silent.
                        if node not in ("__start__", "__end__") and node not in _WARNED_UNMAPPED_NODES:
                            _WARNED_UNMAPPED_NODES.add(node)
                            sys.stderr.write(
                                f"[full_debate] unmapped graph node '{node}' "
                                f"dropped from wire (upstream rename?)\n"
                            )
                        continue

                    agent = _AGENT_OF.get(node, node)

                    # An analyst mid tool-loop is activity, not a finished message.
                    if phase == "analysts" and _last_message_has_tool_calls(delta):
                        yield {
                            "type": "agent.activity",
                            "agent": agent,
                            "node": node,
                            "status": "using_tools",
                        }
                        continue

                    if last_phase is not None and phase != last_phase:
                        yield {"type": "phase.transition", "from": last_phase, "to": phase}
                    last_phase = phase

                    content = _extract_content(node, delta, phase)
                    event: Dict[str, Any] = {
                        "type": "agent.message",
                        "agent": agent,
                        "phase": phase,
                        "content": content,
                        "node": node,
                    }
                    rnd = _round_from_delta(delta, phase)
                    if rnd is not None:
                        event["round"] = rnd
                    yield event
                    yield _cost_event()

        except TokenCapExceeded as exc:
            aborted = True
            yield {
                "type": "run.token_cap",
                "used": meter.total,
                "cap": token_cap,
                "message": str(exc),
            }
        except CostCapExceeded:
            aborted = True
            yield _cost_cap_event()
        except Exception as exc:  # noqa: BLE001 - surface any node failure as a terminal event
            yield {
                "type": "run.error",
                "error": f"{type(exc).__name__}: {exc}",
            }
            return

        if not aborted and meter.tripped:
            # The USD stop fired but a node caught the raise and carried on
            # with fallback text. The meter keeps refusing calls, so spend is
            # safe, but the assessment would be built on truncated output:
            # end the run as a cost-cap stop instead of reporting it complete.
            aborted = True
            yield _cost_cap_event()

        if aborted:
            return

        decision = _parse_pm_decision(final_state)

        # Score the bull/bear thesis strengths + risk level with one extra
        # quick-model call (metered by the same token meter, so its cost is in
        # the finalized total; degrades to null strengths on any failure).
        # asyncio.to_thread keeps the sync invoke off the event loop, same as
        # the graph stream itself. If the call could cross the USD limit we
        # skip it: the assessment is complete without the strength bars, and
        # the meter would refuse the call anyway (that raise is swallowed by
        # _score_thesis_strengths like any scoring failure).
        empty_strengths = {
            "bull_strength": None,
            "bear_strength": None,
            "risk_level": None,
        }
        if meter.next_call_could_exceed():
            strengths = empty_strengths
        else:
            try:
                strengths = await asyncio.to_thread(
                    _score_thesis_strengths, graph, final_state
                )
            except Exception:
                strengths = empty_strengths
        decision.update(strengths)

        # Persist to the memory log so the NEXT same-ticker run can reflect on
        # this decision. Bypassing the library's _run_graph means we replicate
        # this hook explicitly; skipping it silently disables cross-run learning.
        try:
            if final_state is not None and final_state.get("final_trade_decision"):
                graph.memory_log.store_decision(
                    ticker=ticker,
                    trade_date=trade_date,
                    final_trade_decision=final_state["final_trade_decision"],
                )
        except Exception:
            pass  # memory is best-effort; never fail the run over it

        yield {
            "type": "session.complete",
            "ticker": ticker,
            "trade_date": trade_date,
            "decision": decision,
            "live": True,
            "engine": "full",
            "provider": merged.get("llm_provider"),
            # `model` mirrors the free path's session.complete so storage's
            # History row is populated; `deep_model`/`quick_model` add the split.
            "model": merged.get("deep_think_llm"),
            "deep_model": merged.get("deep_think_llm"),
            "quick_model": merged.get("quick_think_llm"),
            "auth_kind": auth_kind,
            "input_tokens": meter.input_tokens,
            "output_tokens": meter.output_tokens,
            "estimated_cost_usd": round(_run_cost(auth_kind, merged, meter), 4),
        }
        # Only reached once the consumer asked for the NEXT event, i.e. after
        # the server sent and captured session.complete. If the user closes
        # the window during the yield (WebSocket disconnect), the generator is
        # closed at the yield, this line never runs, and the reservation is
        # finalized as unrecorded so the paid run still counts toward the caps.
        completed = True
    finally:
        _finalize_reservation(
            reservation_id, auth_kind, merged, meter, completed=completed
        )


def _extract_content(node: str, delta: Dict[str, Any], phase: str) -> str:
    """Pull the human-readable text a node produced for its transcript message."""
    # Analysts write their report into a phase-specific report key.
    for key in ("market_report", "fundamentals_report", "sentiment_report", "news_report"):
        if delta.get(key):
            return str(delta[key])
    # Researcher / risk turns carry their text in the debate-state history fields.
    inv = delta.get("investment_debate_state") or {}
    if inv.get("current_response"):
        return str(inv["current_response"])
    if inv.get("judge_decision"):
        return str(inv["judge_decision"])
    # Risk turns need a node-keyed lookup, NOT first-non-empty: the risk
    # debate state carries a SEPARATE current_*_response field per speaker
    # and each node re-emits the whole state, so the aggressive analyst's
    # line (written first, never cleared) used to be returned for the
    # conservative / neutral / PM turns too.
    risk = delta.get("risk_debate_state") or {}
    risk_key = _RISK_NODE_RESPONSE_KEY.get(node)
    if risk_key and risk.get(risk_key):
        return str(risk[risk_key])
    if node == "Portfolio Manager" and risk.get("judge_decision"):
        return str(risk["judge_decision"])
    if delta.get("trader_investment_plan"):
        return str(delta["trader_investment_plan"])
    if delta.get("final_trade_decision"):
        return str(delta["final_trade_decision"])
    # Fall back to the last message's text.
    msgs = delta.get("messages") or []
    if msgs:
        return str(getattr(msgs[-1], "content", "") or "")
    return ""
