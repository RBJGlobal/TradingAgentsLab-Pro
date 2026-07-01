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

* The real Portfolio Manager emits a 5-tier rating (Buy / Overweight / Hold /
  Underweight / Sell) with no confidence field, rendered as markdown. The free
  app's ACTION=/CONFIDENCE= regex parser does not match that shape, so we parse
  the PM markdown here and map it onto the existing 3-tier decision contract
  while also surfacing the richer native fields.
"""

from __future__ import annotations

import math
import re
from typing import Any, AsyncIterator, Dict, List, Optional

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
    "Social Analyst": "sentiment_analyst",
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

# Rating -> 3-tier action, and a documented confidence heuristic so the existing
# decision card (which expects {action, confidence}) keeps working. The native
# 5-tier rating is passed through alongside for the Pro-richer display.
_RATING_TO_ACTION = {
    "buy": "BUY",
    "overweight": "BUY",
    "hold": "HOLD",
    "underweight": "SELL",
    "sell": "SELL",
}
_RATING_TO_CONFIDENCE = {
    "buy": 0.85,
    "overweight": 0.65,
    "hold": 0.5,
    "underweight": 0.65,
    "sell": 0.85,
}


class TokenCapExceeded(Exception):
    """Raised by the in-run token meter when the running total crosses the cap."""


class _TokenMeter(BaseCallbackHandler):
    """Meter token usage across the whole graph run and abort when over cap.

    ``raise_error = True`` is mandatory: without it LangChain logs and swallows
    exceptions raised inside callbacks, so the cap would never actually stop the
    run. With it, the raise propagates out of ``graph.astream`` and halts.
    """

    raise_error = True

    def __init__(self, cap: Optional[int]) -> None:
        self.cap = cap
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

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
        if self.cap is not None and self.total >= self.cap:
            raise TokenCapExceeded(f"token cap {self.cap} exceeded ({self.total})")


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
    """Parse the Portfolio Manager markdown into the wire decision contract.

    Maps the native 5-tier rating onto the existing 3-tier ``action`` and a
    heuristic ``confidence`` (so the current decision card keeps working), while
    passing through the richer native fields for the Pro display.
    """
    text = ""
    if final_state:
        text = final_state.get("final_trade_decision") or ""

    rating_match = re.search(r"\*\*Rating\*\*:\s*([A-Za-z]+)", text)
    rating = rating_match.group(1).strip() if rating_match else ""
    rating_key = rating.lower()

    action = _RATING_TO_ACTION.get(rating_key, "HOLD")
    confidence = _RATING_TO_CONFIDENCE.get(rating_key, 0.5)

    summary_match = re.search(
        r"\*\*Executive Summary\*\*:\s*(.+?)(?:\n\*\*|\Z)", text, re.DOTALL
    )
    thesis_match = re.search(
        r"\*\*Investment Thesis\*\*:\s*(.+?)(?:\n\*\*|\Z)", text, re.DOTALL
    )
    reasoning = (summary_match.group(1).strip() if summary_match else "").strip()
    if not reasoning:
        reasoning = text.strip() or "No decision text produced."

    price_match = re.search(r"\*\*Price Target\*\*:\s*([\d.]+)", text)
    horizon_match = re.search(r"\*\*Time Horizon\*\*:\s*(.+?)(?:\n|\Z)", text)

    return {
        "action": action,
        "confidence": confidence,
        "reasoning": reasoning,
        # Pro-richer native fields (ignored by the current UI, surfaced in P2).
        "rating": rating or None,
        "investment_thesis": (thesis_match.group(1).strip() if thesis_match else None),
        "price_target": (float(price_match.group(1)) if price_match else None),
        "time_horizon": (horizon_match.group(1).strip() if horizon_match else None),
    }


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


async def full_debate(
    ticker: str,
    trade_date: str,
    *,
    config: Optional[Dict[str, Any]] = None,
    selected_analysts: Optional[List[str]] = None,
    token_cap: Optional[int] = None,
    past_context: str = "",
) -> AsyncIterator[Dict[str, Any]]:
    """Drive the full LangGraph diligence graph, yielding UI-compatible events.

    Event stream (extends the free app's contract):
      session.start, graph.plan, phase.transition, agent.activity, agent.message,
      cost.usage, run.token_cap (on abort), run.error (on failure), session.complete.
    """
    merged = _build_config(config)
    analysts = selected_analysts or ["market", "social", "news", "fundamentals"]
    meter = _TokenMeter(token_cap)

    # A fresh graph per session: TradingAgentsGraph holds mutable instance state
    # (self.ticker / self.curr_state), so it must not be shared across runs.
    graph = TradingAgentsGraph(
        selected_analysts=analysts,
        debug=False,
        config=merged,
        callbacks=[meter],
    )
    state = graph.propagator.create_initial_state(ticker, trade_date, past_context=past_context)

    yield {"type": "session.start", "ticker": ticker, "trade_date": trade_date}
    # graph.plan lets the UI render honest totals for the deterministic phases.
    # Analyst per-phase counts are NOT included: their tool loops make the count
    # non-deterministic, so the UI tracks analysts by explicit completion, not a
    # fraction.
    yield {
        "type": "graph.plan",
        "analysts": analysts,
        "max_debate_rounds": int(merged.get("max_debate_rounds", 1)),
        "max_risk_rounds": int(merged.get("max_risk_discuss_rounds", 1)),
        "deep_model": merged.get("deep_think_llm"),
        "quick_model": merged.get("quick_think_llm"),
    }

    final_state: Optional[Dict[str, Any]] = None
    last_phase: Optional[str] = None
    aborted = False

    def _cost_event() -> Dict[str, Any]:
        return {
            "type": "cost.usage",
            "input_tokens": meter.input_tokens,
            "output_tokens": meter.output_tokens,
            # Cost is finalized against the provider on session.complete; during
            # the run we report tokens and let the UI's cost-guard poll fill USD.
            "est_cost_usd": 0.0,
            "free": merged.get("llm_provider") in ("local",),
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
                    agent = _AGENT_OF.get(node.replace("tools_", "").capitalize() + " Analyst")
                    yield {
                        "type": "agent.activity",
                        "agent": agent or node,
                        "node": node,
                        "status": "using_tools",
                    }
                    continue

                phase = _PHASE_OF.get(node)
                if phase is None:
                    continue  # START/END or an unmapped internal node

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
    except Exception as exc:  # noqa: BLE001 - surface any node failure as a terminal event
        yield {
            "type": "run.error",
            "error": f"{type(exc).__name__}: {exc}",
        }
        return

    if aborted:
        return

    decision = _parse_pm_decision(final_state)

    # Persist to the memory log so the NEXT same-ticker run can reflect on this
    # decision. Bypassing the library's _run_graph means we replicate this hook
    # explicitly; skipping it silently disables cross-run learning.
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
        "deep_model": merged.get("deep_think_llm"),
        "quick_model": merged.get("quick_think_llm"),
        "input_tokens": meter.input_tokens,
        "output_tokens": meter.output_tokens,
        "estimated_cost_usd": 0.0,
    }


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
    risk = delta.get("risk_debate_state") or {}
    for key in (
        "current_aggressive_response",
        "current_conservative_response",
        "current_neutral_response",
        "judge_decision",
    ):
        if risk.get(key):
            return str(risk[key])
    if delta.get("trader_investment_plan"):
        return str(delta["trader_investment_plan"])
    if delta.get("final_trade_decision"):
        return str(delta["final_trade_decision"])
    # Fall back to the last message's text.
    msgs = delta.get("messages") or []
    if msgs:
        return str(getattr(msgs[-1], "content", "") or "")
    return ""
