"""Pro Cost Guard: the full-graph estimate, the mid-run USD stop, and the
ledger fixes that make an aborted run count against the caps.

Covers (founder decisions 2026-11-14):
- pro_reservation_estimate: calibration, analyst count, round growth, the
  deep/quick split, unknown models, OAuth/local.
- the stored mid-run limit: cap headroom for normal runs, 3x the estimate
  for override / disabled / no-cap runs, none for OAuth.
- _TokenMeter: halts before a call that could cross the limit (overshoot at
  most one call), through a real LangChain chat model and a real LangGraph.
- full_debate end to end on a fake graph: run.cost_cap event, the reservation
  finalized with the real partial cost, and that cost counted in spend.
- /cost-guard/reserve vs the WS auto-reserve agree for the same config.
- default caps $5 / $15 / $45 on a fresh DB; an existing DB keeps its caps
  and gains the new reservation columns; the 60-minute Pro TTL.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, TypedDict

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from engine import cost_guard, full_debate as fd, llm_providers, storage
from engine.cost_guard import (
    PRO_ESTIMATE_FACTOR,
    PRO_RESERVATION_TTL_SECONDS,
    RESERVATION_TTL_SECONDS,
    RUNAWAY_MULTIPLIER,
    pro_node_budgets,
    pro_reservation_estimate,
)
from engine.server import build_app

TOKEN = "test-token-1234"
SONNET = "claude-sonnet-4-6"


def _est(deep: str = SONNET, quick: Optional[str] = None, **kw: Any) -> float:
    kw.setdefault("auth_kind", "api_key")
    kw.setdefault("provider", "anthropic")
    return pro_reservation_estimate(deep_model=deep, quick_model=quick or deep, **kw)


def _section(budgets, prefixes) -> tuple[int, int]:
    rows = [b for b in budgets if b.node.startswith(prefixes)]
    return sum(b.input_tokens for b in rows), sum(b.output_tokens for b in rows)


# ---- Estimator --------------------------------------------------------------


def test_default_config_is_about_1_4x_the_reference_run():
    """Reference run: 164,419 in / 28,564 out. The default budget is ~1.4x."""
    b = pro_node_budgets()
    tin = sum(x.input_tokens for x in b)
    tout = sum(x.output_tokens for x in b)
    assert 225_000 <= tin <= 240_000
    assert 38_000 <= tout <= 42_000
    assert PRO_ESTIMATE_FACTOR == 1.4


def test_default_sonnet_4_6_lands_between_1_and_1_60():
    assert 1.0 < _est() < 1.6


def test_one_analyst_costs_less_than_four():
    one = _est(selected_analysts=["market"])
    four = _est(selected_analysts=["market", "social", "news", "fundamentals"])
    assert one < four
    # Fewer analysts also shrink the DOWNSTREAM context (fewer reports).
    b1 = pro_node_budgets(selected_analysts=["market"])
    b4 = pro_node_budgets()
    bull1 = next(x for x in b1 if x.node == "bull_researcher")
    bull4 = next(x for x in b4 if x.node == "bull_researcher")
    assert bull1.input_tokens < bull4.input_tokens


def test_none_or_empty_analysts_means_all_four():
    assert _est(selected_analysts=None) == _est(
        selected_analysts=["market", "social", "news", "fundamentals"]
    )
    inp = cost_guard.normalize_pro_fields({"selected_analysts": []}, fallback_model=SONNET)
    assert inp.selected_analysts == list(cost_guard.PRO_ALL_ANALYSTS)


def test_debate_and_risk_input_grow_faster_than_linearly():
    """Each extra round adds turns that read the whole earlier debate, so the
    debate and risk sections more than double from 1/1 to 2/2 rounds. Only
    those sections: analysts don't repeat with rounds."""
    one = pro_node_budgets(max_debate_rounds=1, max_risk_discuss_rounds=1)
    two = pro_node_budgets(max_debate_rounds=2, max_risk_discuss_rounds=2)
    debate = ("bull_researcher", "bear_researcher")
    risk = ("risk_aggressive", "risk_conservative", "risk_neutral")
    for section in (debate, risk):
        in1, out1 = _section(one, section)
        in2, out2 = _section(two, section)
        assert in2 > 2 * in1, section
        assert out2 == 2 * out1, section
    assert _est(max_debate_rounds=2, max_risk_discuss_rounds=2) > _est()


def test_manager_nodes_are_priced_at_the_deep_model():
    budgets = pro_node_budgets()
    deep_nodes = {b.node for b in budgets if b.tier == "deep"}
    assert deep_nodes == {"research_manager", "portfolio_manager"}
    # Swapping only the deep model changes the price by exactly the manager
    # nodes' tokens at the rate difference.
    cheap = _est(deep=SONNET, quick=SONNET)
    pricey = _est(deep="claude-opus-4-8", quick=SONNET)
    din = sum(b.input_tokens for b in budgets if b.tier == "deep")
    dout = sum(b.output_tokens for b in budgets if b.tier == "deep")
    opus = llm_providers._COST_PER_M_TOKENS["claude-opus-4-8"]
    son = llm_providers._COST_PER_M_TOKENS[SONNET]
    delta = (din * (opus["input"] - son["input"]) + dout * (opus["output"] - son["output"])) / 1e6
    assert pricey - cheap == pytest.approx(delta)


def test_unknown_model_gets_a_ceiling_never_zero():
    for model, provider in (
        ("mystery-vendor/model-x", "openrouter"),
        ("claude-brand-new-9", "anthropic"),
        ("deepseek-v9", None),
        ("totally-unknown", None),
    ):
        assert _est(deep=model, provider=provider) > 1.0, model


def test_oauth_and_local_are_zero():
    for auth in ("oauth", "local"):
        assert _est(deep="gpt-6-luna", provider="openai", auth_kind=auth) == 0.0
        assert _est(auth_kind=auth) == 0.0


def test_reasoning_models_scale_billed_output():
    assert cost_guard.pro_model_reasons("claude-sonnet-5-5", "anthropic")
    assert not cost_guard.pro_model_reasons(SONNET, "anthropic")
    # Pro sends no reasoning_effort by default, so gpt-5.1+ DOES think here
    # (unlike Lite, which sends "none").
    assert cost_guard.pro_model_reasons("gpt-5.5", "openai")
    assert cost_guard.pro_model_reasons("openai/gpt-5.1", "openrouter")
    assert not cost_guard.pro_model_reasons("gpt-4o-mini", "openai")
    assert not cost_guard.pro_model_reasons("gpt-5-chat-latest", "openai")
    # Scaling touches output only: input tokens are the same either way.
    b = pro_node_budgets()
    tin = sum(x.input_tokens for x in b)
    tout = sum(x.output_tokens for x in b)
    r = llm_providers.rates_for("claude-sonnet-5-5")
    expected = (tin * r["input"] + tout * cost_guard.PRO_REASONING_OUTPUT_FACTOR * r["output"]) / 1e6
    assert _est(deep="claude-sonnet-5-5") == pytest.approx(expected)


# ---- Stored mid-run limit ---------------------------------------------------


def _pro(**kw: Any) -> dict:
    base = {"deep_think_llm": SONNET, "quick_think_llm": SONNET,
            "max_debate_rounds": 1, "max_risk_discuss_rounds": 1}
    base.update(kw)
    return base


def test_normal_run_limit_is_the_smallest_cap_headroom(tmp_db):
    cost_guard.update_config(cap_daily_usd=5.0, cap_weekly_usd=15.0, cap_monthly_usd=45.0)
    first = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400,
                               provider="anthropic", pro=_pro())
    # First run: daily headroom is the whole $5 cap.
    assert first.limit_reason == "cap" and first.limit_dimension == "daily"
    assert first.usd_limit == pytest.approx(5.0)
    # Second run while the first is live: headroom = cap - other reservation.
    second = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400,
                                provider="anthropic", pro=_pro())
    assert second.usd_limit == pytest.approx(5.0 - first.est_cost_usd)
    lim = cost_guard.run_usd_limit(second.reservation_id)
    assert lim is not None and lim.limit_usd == pytest.approx(second.usd_limit)
    assert lim.reason == "cap" and lim.dimension == "daily"


def test_weekly_cap_can_be_the_binding_one(tmp_db):
    cost_guard.update_config(cap_daily_usd=0.0, cap_weekly_usd=3.0, cap_monthly_usd=45.0)
    r = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    assert (r.limit_reason, r.limit_dimension) == ("cap", "weekly")
    assert r.usd_limit == pytest.approx(3.0)


def test_override_limit_is_three_times_the_estimate(tmp_db):
    cost_guard.update_config(cap_daily_usd=0.01)
    r = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400,
                           override=True, pro=_pro())
    assert RUNAWAY_MULTIPLIER == 3.0
    assert r.limit_reason == "runaway"
    assert r.usd_limit == pytest.approx(3 * r.est_cost_usd)


def test_disabled_or_no_usd_cap_gets_the_runaway_stop(tmp_db):
    cost_guard.update_config(enabled=False)
    r = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    assert r.limit_reason == "runaway" and r.usd_limit == pytest.approx(3 * r.est_cost_usd)
    cost_guard.update_config(enabled=True, cap_daily_usd=0, cap_weekly_usd=0, cap_monthly_usd=0)
    r = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    assert r.limit_reason == "runaway"


def test_oauth_run_has_no_usd_limit(tmp_db):
    r = cost_guard.reserve(model="gpt-6-luna", auth_kind="oauth", max_tokens=400,
                           provider="openai", pro=_pro(deep_think_llm="gpt-6-luna",
                                                       quick_think_llm="gpt-6-luna"))
    assert r.est_cost_usd == 0.0 and r.usd_limit is None
    assert cost_guard.run_usd_limit(r.reservation_id) is None
    assert cost_guard.run_usd_limit("no-such-id") is None


# ---- TTL --------------------------------------------------------------------


def _expires_in_seconds(res) -> float:
    exp = datetime.strptime(res.expires_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (exp - datetime.now(timezone.utc)).total_seconds()


def test_pro_reservations_live_60_minutes_simplified_15(tmp_db):
    assert PRO_RESERVATION_TTL_SECONDS == 60 * 60
    pro = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    lite = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400)
    assert _expires_in_seconds(pro) == pytest.approx(PRO_RESERVATION_TTL_SECONDS, abs=5)
    assert _expires_in_seconds(lite) == pytest.approx(RESERVATION_TTL_SECONDS, abs=5)


def test_expired_reservation_still_records_an_aborted_cost(tmp_db):
    """A run that outlives its TTL is swept (finalized, no cost). If it then
    aborts, its real cost must still land in the ledger."""
    r = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    with sqlite3.connect(str(tmp_db)) as conn:
        conn.execute("UPDATE cost_reservations SET expires_at = ? WHERE id = ?",
                     ("2020-01-01T00:00:00Z", r.reservation_id))
        conn.commit()
    spend, _ = cost_guard.get_state()  # sweeps
    assert spend.daily_usd == 0.0
    assert cost_guard.finalize_reservation(r.reservation_id, actual_cost_usd=0.42, unrecorded=True)
    spend, _ = cost_guard.get_state()
    assert spend.daily_usd == pytest.approx(0.42)


# ---- Aborted runs count against the caps ------------------------------------


def test_aborted_run_cost_counts_and_completed_run_is_not_double_counted(tmp_db):
    aborted = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    cost_guard.finalize_reservation(aborted.reservation_id, actual_cost_usd=0.87, unrecorded=True)
    spend, _ = cost_guard.get_state()
    assert spend.daily_usd == pytest.approx(0.87)
    # A completed run: its cost lives in sessions; finalize must not add it again.
    done = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    storage.write_session_from_events(ticker="NVDA", trade_date="2026-11-13", events=[{
        "type": "session.complete", "decision": {"stance": "neutral", "conviction": 0.5,
                                                 "reasoning": "x"},
        "live": True, "provider": "anthropic", "model": SONNET, "auth_kind": "api_key",
        "input_tokens": 1, "output_tokens": 1, "estimated_cost_usd": 0.5,
    }])
    cost_guard.finalize_reservation(done.reservation_id, actual_cost_usd=0.5, unrecorded=False)
    spend, _ = cost_guard.get_state()
    assert spend.daily_usd == pytest.approx(1.37)


# ---- Default caps + migration of an existing DB -----------------------------


def test_fresh_db_seeds_5_15_45(tmp_db):
    c = cost_guard.get_config()
    assert (c.cap_daily_usd, c.cap_weekly_usd, c.cap_monthly_usd) == (5.0, 15.0, 45.0)
    assert c.cap_sessions_per_day == 0


_OLD_SCHEMA = """
CREATE TABLE cost_guard_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 1,
    cap_daily_usd REAL NOT NULL DEFAULT 1.00,
    cap_weekly_usd REAL NOT NULL DEFAULT 5.00,
    cap_monthly_usd REAL NOT NULL DEFAULT 15.00,
    cap_sessions_per_day INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE cost_reservations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    est_cost_usd REAL NOT NULL,
    auth_kind TEXT NOT NULL,
    override INTEGER NOT NULL DEFAULT 0,
    finalized INTEGER NOT NULL DEFAULT 0,
    finalized_cost_usd REAL
);
INSERT INTO cost_guard_config VALUES (1, 1, 1.00, 5.00, 15.00, 0, '2026-07-01T00:00:00Z');
INSERT INTO cost_reservations VALUES ('old-1', '2026-07-01T00:00:00Z',
    '2026-07-01T00:15:00Z', 0.2, 'api_key', 0, 1, 0.1);
"""


def test_existing_db_with_untouched_old_defaults_is_upgraded_once(tmp_db):
    """Founder decision 2026-11-14: caps still at exactly the old $1/$5/$15
    defaults move to $5/$15/$45 on update; the new columns are added."""
    tmp_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(tmp_db)) as conn:
        conn.executescript(_OLD_SCHEMA)
        conn.commit()
    cost_guard.initialize()
    c = cost_guard.get_config()
    assert (c.cap_daily_usd, c.cap_weekly_usd, c.cap_monthly_usd) == (5.0, 15.0, 45.0)
    with sqlite3.connect(str(tmp_db)) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(cost_reservations)")}
        old = conn.execute("SELECT unrecorded, usd_limit FROM cost_reservations "
                           "WHERE id='old-1'").fetchone()
    assert {"unrecorded", "usd_limit", "limit_reason", "limit_dimension"} <= cols
    assert old == (0, None)  # pre-existing rows are not counted as aborted
    # A default Sonnet 4.6 Pro run (~$1.31) now fits and gets the cap stop.
    r = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    assert r.limit_reason == "cap"
    # One time only: a user who later sets $1/$5/$15 on purpose keeps it.
    cost_guard.update_config(cap_daily_usd=1.0, cap_weekly_usd=5.0, cap_monthly_usd=15.0)
    cost_guard.initialize()
    c = cost_guard.get_config()
    assert (c.cap_daily_usd, c.cap_weekly_usd, c.cap_monthly_usd) == (1.0, 5.0, 15.0)


def test_existing_db_with_custom_caps_keeps_them(tmp_db):
    tmp_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(tmp_db)) as conn:
        conn.executescript(_OLD_SCHEMA.replace(
            "VALUES (1, 1, 1.00, 5.00, 15.00, 0,", "VALUES (1, 1, 2.00, 5.00, 15.00, 0,"))
        conn.commit()
    cost_guard.initialize()
    c = cost_guard.get_config()
    assert (c.cap_daily_usd, c.cap_weekly_usd, c.cap_monthly_usd) == (2.0, 5.0, 15.0)
    # The user's own $2 cap still applies: one ~$1.31 run fits, a second
    # identical run would cross it and is blocked.
    cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    with pytest.raises(cost_guard.CostGuardBlocked):
        cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())


def test_fresh_db_is_not_touched_by_the_upgrade(tmp_db):
    cost_guard.initialize()
    cost_guard.update_config(cap_daily_usd=1.0, cap_weekly_usd=5.0, cap_monthly_usd=15.0)
    cost_guard.initialize()
    c = cost_guard.get_config()
    assert (c.cap_daily_usd, c.cap_weekly_usd, c.cap_monthly_usd) == (1.0, 5.0, 15.0)


# ---- Meter: halts before the limit, overshoot at most one call --------------


def _msg(i: int = 1000, o: int = 100) -> AIMessage:
    return AIMessage(content="ok", usage_metadata={"input_tokens": i, "output_tokens": o,
                                                   "total_tokens": i + o})


def _fake_llm(meter, n: int = 200, **kw):
    return GenericFakeChatModel(messages=iter([_msg(**kw) for _ in range(n)]), callbacks=[meter])


SONNET_RATES = {"input": 3.0, "output": 15.0}  # one 1000/100 call = $0.0045


def test_meter_refuses_the_call_that_could_cross_the_limit():
    meter = fd._TokenMeter(None, rates=SONNET_RATES, usd_limit=0.01)
    llm = _fake_llm(meter)
    made = 0
    with pytest.raises(fd.CostCapExceeded):
        for _ in range(20):
            llm.invoke("hi")
            made += 1
    # $0.009 spent; one more $0.0045 call could reach $0.0135 > $0.01.
    assert made == 2 and meter.calls == 2
    assert meter.spent_usd <= 0.01


def test_meter_overshoot_is_bounded_by_one_call():
    """Calls that grow: the stop still lands within one call of the limit."""
    meter = fd._TokenMeter(None, rates=SONNET_RATES, usd_limit=0.05)
    msgs = iter([_msg(i=500 * (k + 1), o=50) for k in range(100)])
    llm = GenericFakeChatModel(messages=msgs, callbacks=[meter])
    with pytest.raises(fd.CostCapExceeded):
        for _ in range(100):
            llm.invoke("hi")
    assert meter.spent_usd <= 0.05 + meter.max_call_usd


def test_meter_without_limit_or_rates_never_stops():
    for meter in (fd._TokenMeter(None, rates=SONNET_RATES, usd_limit=None),
                  fd._TokenMeter(None, rates=None, usd_limit=0.0001)):
        llm = _fake_llm(meter, n=10)
        for _ in range(10):
            llm.invoke("hi")
        assert meter.calls == 10


class _S(TypedDict, total=False):
    n: int


def test_cost_cap_raise_propagates_out_of_a_langgraph_stream():
    import asyncio

    meter = fd._TokenMeter(None, rates=SONNET_RATES, usd_limit=0.01)
    llm = _fake_llm(meter)

    def node(state: _S) -> _S:
        llm.invoke("hi")
        return {"n": state.get("n", 0) + 1}

    g = StateGraph(_S)
    for name in ("a", "b", "c", "d"):
        g.add_node(name, node)
    g.add_edge(START, "a")
    g.add_edge("a", "b")
    g.add_edge("b", "c")
    g.add_edge("c", "d")
    g.add_edge("d", END)
    graph = g.compile()

    async def run():
        async for _ in graph.astream({"n": 0}):
            pass

    with pytest.raises(fd.CostCapExceeded):
        asyncio.run(run())
    assert meter.calls == 2


# ---- full_debate end to end on a fake graph ---------------------------------


class _FakeGraphState(TypedDict, total=False):
    market_report: str
    investment_debate_state: dict
    risk_debate_state: dict
    trader_investment_plan: str
    final_trade_decision: str


class _FakeTradingGraph:
    """Stands in for TradingAgentsGraph: real LangGraph, real LangChain chat
    model, real callbacks (the meter), fake content. Each node makes one
    1000-in / 100-out call. With SWALLOW set, every node catches LLM errors
    and carries on with fallback text, like upstream's structured-output
    fallback does."""

    SWALLOW = False

    def __init__(self, selected_analysts, debug, config, callbacks):
        self.quick_thinking_llm = GenericFakeChatModel(
            messages=iter([_msg() for _ in range(100)]), callbacks=callbacks
        )
        real = self.quick_thinking_llm
        swallow = self.SWALLOW

        class _Llm:
            def invoke(self, prompt):
                if not swallow:
                    return real.invoke(prompt)
                try:
                    return real.invoke(prompt)
                except Exception:  # noqa: BLE001 - the behaviour under test
                    return AIMessage(content="fallback")

        llm = _Llm()

        def analyst(s):
            llm.invoke("x")
            return {"market_report": "market report"}

        def bull(s):
            llm.invoke("x")
            return {"investment_debate_state": {"bull_history": "bull case",
                                                "bear_history": "", "count": 1,
                                                "current_response": "bull"}}

        def bear(s):
            llm.invoke("x")
            inv = dict(s["investment_debate_state"])
            inv.update(bear_history="bear case", count=2, current_response="bear")
            return {"investment_debate_state": inv}

        def pm(s):
            llm.invoke("x")
            return {"final_trade_decision": "**Rating**: Hold\n**Executive Summary**: ok\n"}

        g = StateGraph(_FakeGraphState)
        g.add_node("Market Analyst", analyst)
        g.add_node("Bull Researcher", bull)
        g.add_node("Bear Researcher", bear)
        g.add_node("Portfolio Manager", pm)
        g.add_edge(START, "Market Analyst")
        g.add_edge("Market Analyst", "Bull Researcher")
        g.add_edge("Bull Researcher", "Bear Researcher")
        g.add_edge("Bear Researcher", "Portfolio Manager")
        g.add_edge("Portfolio Manager", END)
        self.graph = g.compile()

        class _Prop:
            def create_initial_state(self, ticker, trade_date, past_context=""):
                return {}

        class _Mem:
            def get_past_context(self, ticker):
                return ""

            def store_decision(self, **kw):
                pass

        self.propagator = _Prop()
        self.memory_log = _Mem()


async def _drain(gen) -> list[dict]:
    return [e async for e in gen]


def _run_fake(monkeypatch, **kw) -> list[dict]:
    import asyncio

    monkeypatch.setattr(fd, "TradingAgentsGraph", _FakeTradingGraph)
    config = {"llm_provider": "anthropic", "deep_think_llm": SONNET, "quick_think_llm": SONNET}
    return asyncio.run(_drain(fd.full_debate("NVDA", "2026-11-13", config=config, **kw)))


def test_full_debate_stops_at_the_limit_and_bills_the_partial_cost(tmp_db, monkeypatch):
    res = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    events = _run_fake(monkeypatch, reservation_id=res.reservation_id, usd_limit=0.01,
                       usd_limit_reason="cap", usd_limit_dimension="daily",
                       est_cost_usd=res.est_cost_usd)
    types = [e["type"] for e in events]
    assert "session.complete" not in types
    cap = next(e for e in events if e["type"] == "run.cost_cap")
    assert cap["reason"] == "cap" and cap["dimension"] == "daily"
    assert cap["used_usd"] == pytest.approx(0.009)
    assert cap["limit_usd"] == pytest.approx(0.01)
    assert cap["message"] == ("Stopped: this run reached your Cost Guard daily cap after "
                              "spending $0.01. Raise the cap in Settings, Cost Guard, or "
                              "use Override.")
    assert "—" not in cap["message"] and "–" not in cap["message"]
    # Finalized with the actual partial cost, flagged unrecorded, and counted.
    with sqlite3.connect(str(tmp_db)) as conn:
        row = conn.execute("SELECT finalized, finalized_cost_usd, unrecorded FROM "
                           "cost_reservations WHERE id = ?", (res.reservation_id,)).fetchone()
    assert row[0] == 1 and row[1] == pytest.approx(0.009) and row[2] == 1
    spend, _ = cost_guard.get_state()
    assert spend.daily_usd == pytest.approx(0.009)


def test_a_node_that_swallows_the_stop_still_ends_as_cost_cap(tmp_db, monkeypatch):
    monkeypatch.setattr(_FakeTradingGraph, "SWALLOW", True)
    events = _run_fake(monkeypatch, usd_limit=0.01, usd_limit_reason="cap",
                       usd_limit_dimension="daily")
    types = [e["type"] for e in events]
    assert "run.cost_cap" in types and "session.complete" not in types
    cap = next(e for e in events if e["type"] == "run.cost_cap")
    # Every call after the stop was refused, so spend never moved past it.
    assert cap["used_usd"] == pytest.approx(0.009)


def test_stop_button_bills_the_partial_cost(tmp_db, monkeypatch):
    """The user pressing Stop closes the generator mid-run (server.py calls
    aclose on disconnect). The partial cost must be finalized as unrecorded."""
    import asyncio

    monkeypatch.setattr(fd, "TradingAgentsGraph", _FakeTradingGraph)
    res = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    config = {"llm_provider": "anthropic", "deep_think_llm": SONNET, "quick_think_llm": SONNET}

    async def run_then_stop():
        gen = fd.full_debate("NVDA", "2026-11-13", config=config,
                             reservation_id=res.reservation_id)
        async for e in gen:
            if e["type"] == "cost.usage":  # one LLM call has been made
                break
        await gen.aclose()

    asyncio.run(run_then_stop())
    with sqlite3.connect(str(tmp_db)) as conn:
        row = conn.execute("SELECT finalized, finalized_cost_usd, unrecorded FROM "
                           "cost_reservations WHERE id = ?", (res.reservation_id,)).fetchone()
    assert row[0] == 1 and row[1] > 0 and row[2] == 1
    spend, _ = cost_guard.get_state()
    assert spend.daily_usd == pytest.approx(row[1])


def test_runaway_message(tmp_db, monkeypatch):
    events = _run_fake(monkeypatch, usd_limit=0.01, usd_limit_reason="runaway",
                       est_cost_usd=0.0033)
    cap = next(e for e in events if e["type"] == "run.cost_cap")
    assert cap["reason"] == "runaway" and cap["dimension"] is None
    assert "three times its estimate of $0.00" in cap["message"]


def test_full_debate_under_the_limit_completes_and_meters_the_scoring_call(tmp_db, monkeypatch):
    res = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    events = _run_fake(monkeypatch, reservation_id=res.reservation_id, usd_limit=1.0,
                       usd_limit_reason="cap", usd_limit_dimension="daily")
    done = next(e for e in events if e["type"] == "session.complete")
    # 4 graph nodes + 1 thesis-scoring call, each 1000/100 tokens.
    assert (done["input_tokens"], done["output_tokens"]) == (5000, 500)
    assert done["estimated_cost_usd"] == pytest.approx(0.0225)
    usage = [e for e in events if e["type"] == "cost.usage"]
    assert usage and usage[-1]["est_cost_usd"] > 0 and usage[-1]["free"] is False
    with sqlite3.connect(str(tmp_db)) as conn:
        row = conn.execute("SELECT finalized_cost_usd, unrecorded FROM cost_reservations "
                           "WHERE id = ?", (res.reservation_id,)).fetchone()
    assert row[0] == pytest.approx(0.0225) and row[1] == 0


def test_scoring_call_is_skipped_when_it_could_cross_the_limit(tmp_db, monkeypatch):
    # 4 graph calls = $0.018; a 5th call could reach $0.0225 > $0.02.
    events = _run_fake(monkeypatch, usd_limit=0.02, usd_limit_reason="cap",
                       usd_limit_dimension="daily")
    done = next(e for e in events if e["type"] == "session.complete")
    assert done["input_tokens"] == 4000
    assert done["decision"]["bull_strength"] is None


def test_token_cap_abort_is_also_billed_as_unrecorded(tmp_db, monkeypatch):
    res = cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400, pro=_pro())
    events = _run_fake(monkeypatch, reservation_id=res.reservation_id, token_cap=2000)
    assert any(e["type"] == "run.token_cap" for e in events)
    spend, _ = cost_guard.get_state()
    assert spend.daily_usd == pytest.approx(0.009)  # 2 calls billed, not $0


# ---- Endpoint vs WS auto-reserve agreement ----------------------------------


@pytest.fixture
def client(tmp_db):
    app = build_app(token=TOKEN)
    with TestClient(app) as c:
        c.headers["Authorization"] = f"Bearer {TOKEN}"
        yield c


def test_endpoint_and_ws_auto_reserve_agree(client, tmp_db, monkeypatch):
    from engine import server

    async def _none(**_kw):
        return None

    async def _empty(**_kw):
        return []

    monkeypatch.setattr(server, "_fetch_summary_safe", _none)
    monkeypatch.setattr(server, "_fetch_news_safe", _empty)
    seen: dict[str, Any] = {}

    async def fake_full_debate(ticker, trade_date, **kw):
        seen.update(kw)
        if False:  # pragma: no cover - makes this an async generator
            yield {}

    monkeypatch.setattr(fd, "full_debate", fake_full_debate)

    pro_config = {"deep_think_llm": "claude-opus-4-8", "quick_think_llm": SONNET,
                  "max_debate_rounds": 2, "max_risk_discuss_rounds": 1,
                  "selected_analysts": ["market", "news"]}
    body = {"model": "claude-opus-4-8", "auth_kind": "api_key", "max_tokens": 400,
            "provider": "anthropic", "pro": pro_config}
    endpoint_est = client.post("/cost-guard/reserve", json=body).json()["est_cost_usd"]
    check_est = client.post("/cost-guard/check", json=body).json()["est_reservation_usd"]

    with client.websocket_connect(f"/stream?token={TOKEN}") as ws:
        ws.send_json({
            "ticker": "NVDA", "trade_date": "2026-11-13", "engine": "pro",
            "pro_config": pro_config,
            "provider_config": {"provider": "anthropic",
                                "auth": {"type": "api_key", "api_key": "sk-fake"},
                                "model": "claude-opus-4-8", "max_tokens": 400},
        })
        try:
            while True:
                ws.receive_json()
        except Exception:
            pass

    rid = seen["reservation_id"]
    with sqlite3.connect(str(tmp_db)) as conn:
        auto_est = conn.execute("SELECT est_cost_usd FROM cost_reservations WHERE id = ?",
                                (rid,)).fetchone()[0]
    expected = pro_reservation_estimate(
        deep_model="claude-opus-4-8", quick_model=SONNET, auth_kind="api_key",
        provider="anthropic", selected_analysts=["market", "news"],
        max_debate_rounds=2, max_risk_discuss_rounds=1,
    )
    assert auto_est == pytest.approx(expected)
    assert endpoint_est == pytest.approx(round(expected, 6))
    assert check_est == pytest.approx(round(expected, 6))
    # The server handed the reservation's stored limit to the meter.
    assert seen["usd_limit_reason"] == "cap" and seen["usd_limit_dimension"] == "daily"
    assert seen["usd_limit"] == pytest.approx(5.0 - endpoint_est)  # first reservation is live


def test_reserve_without_pro_keeps_the_simplified_estimate(client):
    body = {"model": "gpt-4o-mini", "auth_kind": "api_key", "max_tokens": 400}
    est = client.post("/cost-guard/reserve", json=body).json()["est_cost_usd"]
    assert est == pytest.approx(round(cost_guard.worst_case_reservation(
        model="gpt-4o-mini", auth_kind="api_key", max_tokens=400), 6))
