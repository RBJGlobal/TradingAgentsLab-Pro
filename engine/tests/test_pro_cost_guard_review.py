"""Review follow-up tests for Pro Cost Guard (founder NO-GO fixes, 2026-11-14).

Covers: per-call model pricing in _TokenMeter, refresh_run_limit (live cap
headroom, raised estimate), the never-loosen rule, the session.complete
disconnect window (M1), mark_unrecorded, live_debate unrecorded flag, and the
duplicate-column migration race.
"""

from __future__ import annotations

import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine import cost_guard, full_debate as fd, live_debate
from engine.live_debate import ProviderConfig, _Agent
from engine.tests.test_pro_cost_guard import (
    SONNET,
    _FakeTradingGraph,
    _OLD_SCHEMA,
    _pro,
    _run_fake,
)

FALLBACK = {"input": 15.0, "output": 75.0}
RATES = {"model-a": {"input": 1.0, "output": 2.0}, "model-b": {"input": 10.0, "output": 20.0}}


def _meter(**kw):
    kw.setdefault("rates", FALLBACK)
    kw.setdefault("rate_for", lambda m: RATES.get(m))
    return fd._TokenMeter(None, **kw)


def _resp_llm_output(i, o):
    return SimpleNamespace(llm_output={"usage": {"input_tokens": i, "output_tokens": o}},
                           generations=[])


def _resp_generations(i, o):
    msg = SimpleNamespace(usage_metadata={"input_tokens": i, "output_tokens": o})
    return SimpleNamespace(llm_output=None, generations=[[SimpleNamespace(message=msg)]])


# ---- 1-3: meter pricing -----------------------------------------------------


@pytest.mark.parametrize("make", [_resp_llm_output, _resp_generations])
def test_meter_prices_each_call_at_its_own_model(make):
    m = _meter()
    m.on_chat_model_start({}, [], run_id=1, invocation_params={"model": "model-a"})
    m.on_llm_end(make(1_000_000, 0), run_id=1)
    assert m.spent_usd == pytest.approx(1.0)
    m.on_chat_model_start({}, [], run_id=2, invocation_params={"model": "model-b"})
    m.on_llm_end(make(1_000_000, 0), run_id=2)
    assert m.spent_usd == pytest.approx(11.0)


def test_unknown_model_call_is_priced_at_fallback_rates():
    m = _meter()
    m.on_llm_end(_resp_llm_output(1_000_000, 0), run_id=99)  # no start event
    assert m.spent_usd == pytest.approx(15.0)
    # A model the resolver does not know also falls back.
    m.on_chat_model_start({}, [], run_id=5, invocation_params={"model": "mystery"})
    m.on_llm_end(_resp_llm_output(1_000_000, 0), run_id=5)
    assert m.spent_usd == pytest.approx(30.0)


def test_free_meter_stays_at_zero():
    m = fd._TokenMeter(None, rates=None, rate_for=lambda x: RATES["model-b"])
    m.on_chat_model_start({}, [], run_id=1, invocation_params={"model": "model-b"})
    m.on_llm_end(_resp_llm_output(1_000_000, 1_000_000), run_id=1)
    assert m.spent_usd == 0.0 and m.calls == 1


def test_metadata_ls_model_name_used_when_no_invocation_model():
    m = _meter()
    m.on_chat_model_start({}, [], run_id=1, invocation_params={},
                          metadata={"ls_model_name": "model-a"})
    m.on_llm_end(_resp_llm_output(1_000_000, 0), run_id=1)
    assert m.spent_usd == pytest.approx(1.0)


def test_run_cost_is_meter_total_for_api_key_and_zero_for_oauth_local():
    m = _meter()
    m._spent_usd = 3.21
    assert fd._run_cost("api_key", {}, m) == pytest.approx(3.21)
    assert fd._run_cost("oauth", {}, m) == 0.0
    assert fd._run_cost("local", {}, m) == 0.0


# ---- 4-5: refresh_run_limit -------------------------------------------------


def _est_in_db(db, rid):
    with sqlite3.connect(str(db)) as conn:
        return conn.execute("SELECT est_cost_usd FROM cost_reservations WHERE id=?",
                            (rid,)).fetchone()[0]


def _reserve_pro(**kw):
    return cost_guard.reserve(model=SONNET, auth_kind="api_key", max_tokens=400,
                              provider="anthropic", pro=_pro(), **kw)


def test_refresh_raises_estimate_and_returns_live_headroom(tmp_db):
    a = _reserve_pro()
    head = cost_guard.refresh_run_limit(a.reservation_id, spent_usd=2.0, next_call_usd=0.5)
    assert _est_in_db(tmp_db, a.reservation_id) >= 2.5
    assert head == pytest.approx(5.0)  # alone: nothing else counts against the cap
    b = _reserve_pro()
    a_est = _est_in_db(tmp_db, a.reservation_id)
    assert b.usd_limit == pytest.approx(5.0 - a_est)
    head_a = cost_guard.refresh_run_limit(a.reservation_id, spent_usd=2.0, next_call_usd=0.5)
    assert head_a == pytest.approx(5.0 - b.est_cost_usd)


def test_refresh_never_lowers_the_estimate(tmp_db):
    a = _reserve_pro()
    cost_guard.refresh_run_limit(a.reservation_id, spent_usd=0.0, next_call_usd=0.0)
    assert _est_in_db(tmp_db, a.reservation_id) == pytest.approx(a.est_cost_usd)


def test_refresh_override_returns_stored_runaway_limit(tmp_db):
    r = _reserve_pro(override=True)
    assert r.limit_reason == "runaway"
    got = cost_guard.refresh_run_limit(r.reservation_id, spent_usd=0.1, next_call_usd=0.1)
    assert got == pytest.approx(r.usd_limit)


def test_refresh_unknown_or_none_id_returns_none(tmp_db):
    assert cost_guard.refresh_run_limit("no-such-id", spent_usd=1.0, next_call_usd=1.0) is None
    assert cost_guard.refresh_run_limit(None, spent_usd=1.0, next_call_usd=1.0) is None


# ---- 6: never loosen --------------------------------------------------------


def test_refresh_returning_a_bigger_limit_never_loosens_the_meter(tmp_db, monkeypatch):
    monkeypatch.setattr(cost_guard, "refresh_run_limit", lambda *a, **k: 100.0)
    res = _reserve_pro()
    events = _run_fake(monkeypatch, reservation_id=res.reservation_id, usd_limit=0.01,
                       usd_limit_reason="cap", usd_limit_dimension="daily",
                       est_cost_usd=res.est_cost_usd)
    types = [e["type"] for e in events]
    assert "run.cost_cap" in types and "session.complete" not in types
    cap = next(e for e in events if e["type"] == "run.cost_cap")
    assert cap["limit_usd"] == pytest.approx(0.01)


def test_refresh_returning_a_smaller_limit_tightens_the_meter(tmp_db, monkeypatch):
    monkeypatch.setattr(cost_guard, "refresh_run_limit", lambda *a, **k: 0.005)
    res = _reserve_pro()
    events = _run_fake(monkeypatch, reservation_id=res.reservation_id, usd_limit=1.0,
                       usd_limit_reason="cap", usd_limit_dimension="daily")
    cap = next(e for e in events if e["type"] == "run.cost_cap")
    assert cap["limit_usd"] == pytest.approx(0.005)


# ---- 7: M1 disconnect at session.complete -----------------------------------


def _row(db, rid):
    with sqlite3.connect(str(db)) as conn:
        return conn.execute("SELECT finalized, finalized_cost_usd, unrecorded FROM "
                            "cost_reservations WHERE id = ?", (rid,)).fetchone()


def test_close_at_session_complete_finalizes_as_unrecorded_and_counts(tmp_db, monkeypatch):
    monkeypatch.setattr(fd, "TradingAgentsGraph", _FakeTradingGraph)
    res = _reserve_pro()
    config = {"llm_provider": "anthropic", "deep_think_llm": SONNET, "quick_think_llm": SONNET}

    async def go():
        gen = fd.full_debate("NVDA", "2026-11-13", config=config,
                             reservation_id=res.reservation_id, usd_limit=1.0,
                             usd_limit_reason="cap", usd_limit_dimension="daily")
        async for e in gen:
            if e["type"] == "session.complete":
                break
        await gen.aclose()

    asyncio.run(go())
    fin, cost, unrec = _row(tmp_db, res.reservation_id)
    assert fin == 1 and unrec == 1 and cost == pytest.approx(0.0225)
    spend, _ = cost_guard.get_state()
    assert spend.daily_usd == pytest.approx(0.0225)


def test_exhausting_the_generator_finalizes_as_recorded(tmp_db, monkeypatch):
    res = _reserve_pro()
    _run_fake(monkeypatch, reservation_id=res.reservation_id, usd_limit=1.0,
              usd_limit_reason="cap", usd_limit_dimension="daily")
    fin, cost, unrec = _row(tmp_db, res.reservation_id)
    assert fin == 1 and unrec == 0 and cost == pytest.approx(0.0225)


# ---- 8: mark_unrecorded -----------------------------------------------------


def test_mark_unrecorded_makes_a_finalized_cost_count(tmp_db):
    r = _reserve_pro()
    cost_guard.finalize_reservation(r.reservation_id, actual_cost_usd=0.7, unrecorded=False)
    spend, _ = cost_guard.get_state()
    assert spend.daily_usd == 0.0  # no sessions row, flagged recorded: counts $0
    assert cost_guard.mark_unrecorded(r.reservation_id) is True
    spend, _ = cost_guard.get_state()
    assert spend.daily_usd == pytest.approx(0.7)


def test_mark_unrecorded_unknown_or_empty_id_is_false(tmp_db):
    assert cost_guard.mark_unrecorded("no-such-id") is False
    assert cost_guard.mark_unrecorded(None) is False


# ---- 9: live_debate unrecorded flag -----------------------------------------


class _Adapter:
    def __init__(self, script):
        self._script = list(script)

    async def open(self, *, api_key):
        pass

    async def close(self):
        pass

    async def complete(self, **_kw):
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _cfg():
    return ProviderConfig(provider="openai", auth={"type": "api_key", "api_key": "sk-test"},
                          model="gpt-4o-mini", max_tokens=400)


def _agents():
    return [_Agent(name="technical_analyst", phase="analysts", system_prompt="t"),
            _Agent(name="portfolio_manager", phase="decision", system_prompt="p")]


_PM = ("STANCE=BULLISH\nCONVICTION=0.70\nBULL_STRENGTH=70\nBEAR_STRENGTH=30\n"
       "RISK=MODERATE\nok")


def _capture(monkeypatch):
    calls = []

    def fake(rid, *, actual_cost_usd, unrecorded=False):
        calls.append({"id": rid, "cost": actual_cost_usd, "unrecorded": unrecorded})
        return True

    monkeypatch.setattr("engine.cost_guard.finalize_reservation", fake)
    return calls


def test_live_debate_completed_run_finalizes_recorded(tmp_db, monkeypatch):
    monkeypatch.setattr(live_debate, "_AGENTS", _agents())
    monkeypatch.setattr(live_debate, "adapter_for",
                        lambda _c: _Adapter([("a", 100, 50), (_PM, 200, 80)]))
    calls = _capture(monkeypatch)

    async def go():
        return [e async for e in live_debate.live_debate(
            ticker="NVDA", trade_date="2026-05-24", summary=None, headlines=None,
            config=_cfg(), reservation_id="rid-1")]

    asyncio.run(go())
    assert len(calls) == 1 and calls[0]["unrecorded"] is False


def test_live_debate_closed_early_finalizes_unrecorded(tmp_db, monkeypatch):
    monkeypatch.setattr(live_debate, "_AGENTS", _agents())
    monkeypatch.setattr(live_debate, "adapter_for",
                        lambda _c: _Adapter([("a", 100, 50), (_PM, 200, 80)]))
    calls = _capture(monkeypatch)

    async def go():
        gen = live_debate.live_debate(
            ticker="NVDA", trade_date="2026-05-24", summary=None, headlines=None,
            config=_cfg(), reservation_id="rid-2")
        async for e in gen:
            if e["type"] == "session.start":
                break
        await gen.aclose()

    asyncio.run(go())
    assert len(calls) == 1 and calls[0]["unrecorded"] is True


# ---- 10: migration race -----------------------------------------------------


def _old_conn(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "old.db"))
    conn.executescript(_OLD_SCHEMA)
    return conn


def test_migration_is_idempotent_on_one_connection(tmp_path):
    conn = _old_conn(tmp_path)
    cost_guard._add_missing_reservation_columns(conn)
    cost_guard._add_missing_reservation_columns(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(cost_reservations)")}
    assert {"unrecorded", "usd_limit", "limit_reason", "limit_dimension"} <= cols


class _RaceConn:
    """Reports the columns as missing, then fails ALTER like a lost race."""

    def __init__(self, real, message):
        self._real, self._message = real, message

    def execute(self, sql, *a):
        if sql.startswith("ALTER TABLE"):
            raise sqlite3.OperationalError(self._message)
        return self._real.execute(sql, *a)


def test_duplicate_column_error_is_swallowed(tmp_path):
    conn = _old_conn(tmp_path)
    cost_guard._add_missing_reservation_columns(
        _RaceConn(conn, "duplicate column name: unrecorded"))


def test_other_operational_errors_still_raise(tmp_path):
    conn = _old_conn(tmp_path)
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        cost_guard._add_missing_reservation_columns(_RaceConn(conn, "database is locked"))
