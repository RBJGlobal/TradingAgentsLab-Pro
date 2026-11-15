"""Cost Guard — budget caps + reservation gating for live LLM debates.

Enforces per-(day, week, month) USD spending caps plus an optional
sessions-per-day rate cap. Lives entirely in the Python engine because the
LLM transport, token counts, and cost calculations all happen here — putting
the gate in Electron main would require cross-process TOCTOU sync between
"reservation" (Node) and "finalization" (Python). One process is cleaner.

## Tables

Three new tables join the existing `sessions` schema:

- `cost_guard_config` — single row (id=1) holding the user's cap settings.
- `cost_reservations` — one row per in-flight session. TOCTOU gate.
- `sessions.auth_kind` — additive column on the existing sessions table so
  we can exclude OAuth sessions from the cost-cap aggregation (their
  per-token cost is $0 — they bill against the ChatGPT subscription).

## Flow

1. Renderer calls `check()` to preview whether a debate would fit under caps.
2. If it fits (or user clicks Override), renderer calls `reserve()` — which
   atomically reads current spend, computes a worst-case ceiling for the
   new session, decides allow/deny, and (on allow) inserts a reservation row.
3. The reservation_id rides on the WS start frame.
4. Inside `live_debate.py`'s (or Pro's `full_debate.py`'s) try/finally,
   `finalize_reservation()` updates the row with the actual cost and marks it
   finalized.

## What counts as spend

`_compute_spend()` adds three things per window: completed sessions (the
`sessions` table, written from `session.complete`), live reservations at
their estimate, and finalized reservations flagged `unrecorded=1`. The last
one exists because an ABORTED run (token cap, cost cap, node error, client
disconnect) writes no session row, so without it the money it really spent
would count toward no cap at all. A completed run is never flagged, so it is
never counted twice.

## Pro estimate and mid-run limit

Trading Agents Lab Pro runs the real upstream LangGraph graph, whose LLM calls
have no per-call max_tokens, so no pre-run number is a true maximum. The Pro
estimate (`pro_reservation_estimate`) is therefore a calibrated "about 1.4x a
typical run" figure, and the real protection is a mid-run stop: at reserve
time we store a USD limit on the reservation (`_run_limit`), and the Pro
token meter halts the graph before a call that could cross it:

- Normal run: the limit is the smallest headroom left under any enabled USD
  cap. A run that overshoots its estimate but stays under the cap finishes.
- Override run, Cost Guard disabled, or no USD cap enabled: a runaway stop at
  `RUNAWAY_MULTIPLIER` (3x) the run's estimate.
- OAuth / local: no USD limit (they cost $0); the optional token cap applies.

## TTL & crash recovery

Reservations have a TTL: 15 minutes for the simplified debate
(`RESERVATION_TTL_SECONDS`) and 60 minutes for a Pro full-graph run
(`PRO_RESERVATION_TTL_SECONDS`; a default Pro run took 6 to 11 minutes in
testing, and extra debate rounds stretch that). If the engine is killed
mid-debate, the reservation stays as `finalized=0` until either:

- The next `reserve()` call sweeps it (every reserve runs `_sweep_expired()`)
- The startup sweep runs it (called from `initialize()`)

Until swept, an expired reservation is filtered out of spend aggregation by
the `expires_at > now` clause in `_compute_spend()` — so a hard crash
doesn't permanently inflate apparent spend; at worst a crashed Pro run holds
its estimate for an hour. A run that outlives its TTL is still finalized
with its real cost: finalize keys on `finalized_cost_usd IS NULL`, which a
sweep leaves untouched.

## OAuth policy

OAuth sessions (auth_kind='oauth') skip the cost cap entirely (cost is $0,
billed via subscription) but still count toward the rate cap if enabled.
The architect's call: don't double-charge subscription users on a
per-token cap that doesn't apply to them, but optionally protect their
finite ChatGPT quota with a rate cap.
"""

from __future__ import annotations

import os
import secrets as _secrets
import sqlite3
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Literal, Optional

from .llm_providers import (
    anthropic_thinks_by_default,
    gemini_thinks_by_default,
    infer_provider,
    openai_is_classic_chat_model,
    openai_reasoning_effort,
    openrouter_is_reasoning_model,
    per_token_rates,
)
from .live_debate import MAX_AGENTS_PER_SESSION


# ---- Schema -----------------------------------------------------------------

# Schema version for the CostGuard subsystem. Storage.py owns the master
# version; this is only here so tests + diagnostics can sanity-check.
COST_GUARD_SCHEMA_VERSION = 1


_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS cost_guard_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 1,
    cap_daily_usd REAL NOT NULL DEFAULT 5.00,
    cap_weekly_usd REAL NOT NULL DEFAULT 15.00,
    cap_monthly_usd REAL NOT NULL DEFAULT 45.00,
    cap_sessions_per_day INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cost_reservations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    est_cost_usd REAL NOT NULL,
    auth_kind TEXT NOT NULL,
    override INTEGER NOT NULL DEFAULT 0,
    finalized INTEGER NOT NULL DEFAULT 0,
    finalized_cost_usd REAL,
    unrecorded INTEGER NOT NULL DEFAULT 0,
    usd_limit REAL,
    limit_reason TEXT,
    limit_dimension TEXT
);

CREATE INDEX IF NOT EXISTS cost_reservations_finalized_idx
    ON cost_reservations(finalized, expires_at);
"""

_SEED_CONFIG_SQL = """
INSERT OR IGNORE INTO cost_guard_config (
    id, enabled, cap_daily_usd, cap_weekly_usd, cap_monthly_usd,
    cap_sessions_per_day, updated_at
) VALUES (1, 1, 5.00, 15.00, 45.00, 0, ?);
"""
# Pro defaults ($5 / $15 / $45) set 2026-11-14 (founder decision): one default
# Pro run on Claude Sonnet 4.6 really cost $0.93, so the old $1 daily cap
# could not fit even one run. INSERT OR IGNORE means this only seeds NEW
# databases; existing users keep the caps they already have.

# Columns added to cost_reservations after the first release. CREATE TABLE IF
# NOT EXISTS never alters an existing table, so `initialize()` adds any that
# are missing (additive and nullable or defaulted, so old rows stay valid).
_RESERVATION_ADDED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("unrecorded", "INTEGER NOT NULL DEFAULT 0"),
    ("usd_limit", "REAL"),
    ("limit_reason", "TEXT"),
    ("limit_dimension", "TEXT"),
)


# Reservations expire after this many seconds. Slowest realistic Anthropic
# Claude debate is ~6 min; 15 min covers it with headroom and recovers
# quickly from a hard crash.
RESERVATION_TTL_SECONDS = 15 * 60

# Pro full-graph runs measured 6 to 11 minutes at the default config, and
# extra debate/risk rounds and slow reasoning models stretch that. 60 minutes
# keeps the reservation counting for the whole run while a crashed run still
# frees its slot within the hour.
PRO_RESERVATION_TTL_SECONDS = 60 * 60

# Override runs (and runs with no enabled USD cap) get no cap-based stop, but
# a run that costs this many times its own estimate is almost certainly a
# runaway (a tool loop, a model that never stops thinking) and is ended.
RUNAWAY_MULTIPLIER = 3.0


# ---- Dataclasses ------------------------------------------------------------


@dataclass
class CostGuardConfig:
    enabled: bool
    cap_daily_usd: float
    cap_weekly_usd: float
    cap_monthly_usd: float
    cap_sessions_per_day: int
    updated_at: str


@dataclass
class SpendState:
    """Aggregated spend across the three windows + session counts."""

    daily_usd: float
    weekly_usd: float
    monthly_usd: float
    sessions_today: int


@dataclass
class CheckResult:
    allow: bool
    over_dimension: Optional[str]  # "daily" | "weekly" | "monthly" | "rate" | None
    override_available: bool
    current: SpendState
    config: CostGuardConfig
    est_reservation_usd: float


@dataclass
class ReserveResult:
    reservation_id: str
    est_cost_usd: float
    expires_at: str
    auth_kind: str
    override: bool
    # Mid-run USD limit stored on the reservation (see `_run_limit`). None
    # for OAuth/local runs, which cost $0.
    usd_limit: Optional[float] = None
    limit_reason: Optional[str] = None  # "cap" | "runaway" | None
    limit_dimension: Optional[str] = None  # "daily" | "weekly" | "monthly" | None


@dataclass
class RunLimit:
    """The USD limit a run must not cross, read back by the Pro engine."""

    limit_usd: float
    reason: str  # "cap" (an enabled USD cap) or "runaway" (3x the estimate)
    dimension: Optional[str]  # which cap set the limit, for the message
    est_cost_usd: float


# ---- Window math ------------------------------------------------------------


_WindowName = Literal["day", "week", "month"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    """ISO-8601 in UTC with trailing Z (matches storage.py's format)."""
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _window_start(window: _WindowName, *, now: Optional[datetime] = None) -> str:
    """ISO-8601 start of the window containing `now` (or current UTC time).

    - day: 00:00:00Z of today
    - week: 00:00:00Z of Monday of this ISO week
    - month: 00:00:00Z of the first day of this calendar month
    """
    n = now or _utcnow()
    n = n.astimezone(timezone.utc)
    if window == "day":
        start = n.replace(hour=0, minute=0, second=0, microsecond=0)
    elif window == "week":
        # ISO week starts Monday. weekday() = 0 for Mon, 6 for Sun.
        start = n.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=n.weekday())
    elif window == "month":
        start = n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # pragma: no cover — Literal guards this
        raise ValueError(f"unknown window: {window!r}")
    return _iso(start)


# ---- Worst-case reservation (simplified debate) -----------------------------


def worst_case_reservation(
    *,
    model: str,
    auth_kind: str,
    max_tokens: int,
    provider: Optional[str] = None,
) -> float:
    """Conservative upper-bound USD estimate for a single SIMPLIFIED debate
    (``live_debate.py``: the Telegram bot and any caller without ``pro``).

    OAuth and local sessions always return 0.0: OAuth bills via the ChatGPT
    subscription, local runs on the user's machine.

    Every per-token model is priced through ``per_token_rates``, so a model
    with no table row gets a family ceiling (or the top ceiling), never $0.
    Pass ``provider`` when known; otherwise it is inferred from the model id.

    Assumes all 12 agents max out their output cap (the expensive direction)
    AND the input transcript grows triangularly across agents (later agents
    see all prior turns).
    """
    if auth_kind in ("oauth", "local"):
        return 0.0
    rates = per_token_rates(model, provider)
    n = MAX_AGENTS_PER_SESSION
    # Output: every agent maxes its budget. (Worst case.)
    max_out_tokens = n * max_tokens
    # Input: per-agent ~600 tokens of fixed context, plus prior turns.
    # Sum over agents 0..n-1 of prior agents' output: 0+1+2+…+(n-1) = n*(n-1)/2.
    fixed_input_per_agent = 600
    growth_input_tokens = (n * (n - 1) // 2) * max_tokens
    max_in_tokens = n * fixed_input_per_agent + growth_input_tokens
    return (max_in_tokens * rates["input"] + max_out_tokens * rates["output"]) / 1_000_000


# ---- Pro full-graph estimate ------------------------------------------------
#
# Why a calibrated estimate instead of a worst case: Pro runs the real upstream
# LangGraph graph, whose LLM clients get no per-call max_tokens, and whose
# analysts loop over tools an unknown number of times. No pre-run number is a
# true maximum, so a "worst case" would just be a bigger guess. The founder's
# rule (2026-11-14) is a pre-run estimate of about 1.4x a TYPICAL run, backed
# by a mid-run stop at the cap (see `_run_limit` and full_debate's meter).
#
# Calibration: a real default Pro run (4 analysts, 1 debate round, 1 risk
# round, deep = quick = claude-sonnet-4-6) used 164,419 input / 28,564 output
# tokens. Per node (input, output): market 19.8K/4.2K, social 4.3K/2.5K,
# news 13.0K/3.3K, fundamentals 26.4K/5.5K, bull 13.2K/1.8K, bear 16.9K/2.6K,
# research manager 5.6K/1.4K, trader 5.7K/0.5K, aggressive 13.8K/1.4K,
# conservative 16.6K/2.1K, neutral 20.8K/1.8K, portfolio manager 8.4K/1.4K.
# The constants below are fitted to that run ("raw" tokens), then everything
# is scaled by PRO_ESTIMATE_FACTOR.

PRO_ESTIMATE_FACTOR = 1.4

# Reasoning ("thinking") models bill hidden thinking tokens as output, and the
# upstream graph does not cap thinking. 2.5x the visible output is our budget
# for that: it sits between "thinks a little" and the Lite app's own per-call
# allowance (up to 1200 thinking tokens on a 400-token answer, i.e. 4x). It
# scales BILLED output only; thinking text is not carried into later prompts,
# so it does not grow the downstream context.
PRO_REASONING_OUTPUT_FACTOR = 2.5

PRO_ALL_ANALYSTS: tuple[str, ...] = ("market", "social", "news", "fundamentals")

# Per analyst, raw (input, output, report). Analysts run independently (the
# graph clears messages between them), so their inputs do not stack; "report"
# is the part of the output that later nodes read as context. Caveat: the
# reference run had no Alpaca market data and no Alpha Vantage key, so the
# data-driven analysts (social especially, 4.3K/2.5K) may run heavier with
# full data; the 1.4x factor and the mid-run cap stop absorb that.
_PRO_ANALYST_RAW: dict[str, tuple[int, int, int]] = {
    "market": (19_800, 4_200, 2_500),
    "social": (4_300, 2_500, 1_800),
    "news": (13_000, 3_300, 2_200),
    "fundamentals": (26_400, 5_500, 2_500),
}

# Downstream nodes, raw. "Overhead" is each prompt's fixed text plus the
# cross-run memory; "turn" is one speaker's output in a debate loop. The
# bull/bear and risk prompts also carry every analyst report (added below).
_PRO_DEBATE_OVERHEAD = 4_900   # bull / bear prompt
_PRO_DEBATE_TURN_OUT = 2_220
_PRO_RM_OVERHEAD = 1_200       # research manager (deep): reads the debate
_PRO_RM_OUT = 1_410
_PRO_TRADER_OVERHEAD = 4_300   # trader: reads the research manager's plan
_PRO_TRADER_OUT = 500
_PRO_RISK_OVERHEAD = 5_775     # risk analysts: prompt plus the trader plan
_PRO_RISK_TURN_OUT = 1_765
_PRO_PM_OVERHEAD = 2_600       # portfolio manager (deep): reads risk debate
_PRO_PM_OUT = 1_430
# full_debate's post-graph thesis-scoring call (quick model): three clipped
# 4,000-character excerpts (~3K tokens) plus its prompt; a three-line answer.
_PRO_SCORE_IN = 3_500
_PRO_SCORE_OUT = 100


@dataclass
class NodeBudget:
    """Estimated tokens for one LLM node of a Pro run (already scaled)."""

    node: str
    tier: str  # "quick" | "deep": which configured model runs this node
    input_tokens: int
    output_tokens: int


@dataclass
class ProEstimateInputs:
    """Normalized Pro run shape. Built by `normalize_pro_fields` so the
    /cost-guard endpoints and the WS auto-reserve read a pro config the same
    way (and the same way server._build_pro_library_config does)."""

    deep_model: str
    quick_model: str
    selected_analysts: list[str]
    max_debate_rounds: int
    max_risk_discuss_rounds: int


def _int_rounds(value: Any) -> int:
    # Same coercion as server._build_pro_library_config: int(x or 1), floor 1.
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def normalize_pro_fields(raw: Optional[dict], *, fallback_model: str = "") -> ProEstimateInputs:
    """Read a renderer `pro` / `pro_config` dict into estimator inputs.

    Mirrors server._build_pro_library_config: deep falls back to the run's
    primary model, quick falls back to the primary model and then to deep,
    rounds are int(x or 1). Analysts are filtered to the four known ids;
    missing or empty means all four (full_debate's own default).
    """
    raw = raw if isinstance(raw, dict) else {}
    deep = str(raw.get("deep_think_llm") or fallback_model or "").strip()
    quick = str(raw.get("quick_think_llm") or fallback_model or deep).strip()
    picked = raw.get("selected_analysts")
    analysts: list[str] = []
    if isinstance(picked, (list, tuple)):
        for a in picked:
            a = str(a).strip().lower()
            if a in PRO_ALL_ANALYSTS and a not in analysts:
                analysts.append(a)
    if not analysts:
        analysts = list(PRO_ALL_ANALYSTS)
    return ProEstimateInputs(
        deep_model=deep,
        quick_model=quick or deep,
        selected_analysts=analysts,
        max_debate_rounds=_int_rounds(raw.get("max_debate_rounds", 1)),
        max_risk_discuss_rounds=_int_rounds(raw.get("max_risk_discuss_rounds", 1)),
    )


def pro_node_budgets(
    *,
    selected_analysts: Optional[list[str]] = None,
    max_debate_rounds: int = 1,
    max_risk_discuss_rounds: int = 1,
) -> list[NodeBudget]:
    """Per-node token budgets for a Pro run, scaled by PRO_ESTIMATE_FACTOR.

    Node-to-model mapping follows tradingagents/graph/setup.py: the research
    manager and portfolio manager use the DEEP model; every analyst, both
    researchers, the trader, the three risk analysts, and our thesis-scoring
    call use the QUICK model.

    Context growth: in the bull/bear loop each turn reads every earlier turn,
    so turn i (0-based) carries i prior outputs; same for the aggressive /
    conservative / neutral loop. Total input therefore grows faster than the
    number of rounds (triangular), as it does in the real graph.
    """
    analysts = [a for a in (selected_analysts or PRO_ALL_ANALYSTS) if a in _PRO_ANALYST_RAW]
    if not analysts:
        analysts = list(PRO_ALL_ANALYSTS)
    d_turns = 2 * max(1, int(max_debate_rounds))
    r_turns = 3 * max(1, int(max_risk_discuss_rounds))
    raw: list[tuple[str, str, int, int]] = []

    reports = 0
    for a in analysts:
        a_in, a_out, a_report = _PRO_ANALYST_RAW[a]
        raw.append((f"{a}_analyst", "quick", a_in, a_out))
        reports += a_report

    speakers = ("bull_researcher", "bear_researcher")
    for i in range(d_turns):
        raw.append((speakers[i % 2], "quick",
                    _PRO_DEBATE_OVERHEAD + reports + i * _PRO_DEBATE_TURN_OUT,
                    _PRO_DEBATE_TURN_OUT))
    raw.append(("research_manager", "deep",
                _PRO_RM_OVERHEAD + d_turns * _PRO_DEBATE_TURN_OUT, _PRO_RM_OUT))
    raw.append(("trader", "quick", _PRO_TRADER_OVERHEAD + _PRO_RM_OUT, _PRO_TRADER_OUT))

    risk = ("risk_aggressive", "risk_conservative", "risk_neutral")
    for j in range(r_turns):
        raw.append((risk[j % 3], "quick",
                    _PRO_RISK_OVERHEAD + reports + _PRO_TRADER_OUT + j * _PRO_RISK_TURN_OUT,
                    _PRO_RISK_TURN_OUT))
    raw.append(("portfolio_manager", "deep",
                _PRO_PM_OVERHEAD + _PRO_TRADER_OUT + r_turns * _PRO_RISK_TURN_OUT,
                _PRO_PM_OUT))
    raw.append(("thesis_scoring", "quick", _PRO_SCORE_IN, _PRO_SCORE_OUT))

    f = PRO_ESTIMATE_FACTOR
    return [
        NodeBudget(node=n, tier=t, input_tokens=round(i * f), output_tokens=round(o * f))
        for (n, t, i, o) in raw
    ]


def pro_model_reasons(model: str, provider: Optional[str] = None) -> bool:
    """Whether a model spends billed thinking tokens on the upstream graph.

    Differs from the Lite app's `thinking_allowance` on OpenAI: Lite sends
    reasoning_effort "none" to gpt-5.1+, so they do not think there. Pro's
    upstream clients send no effort unless the user set one, so every OpenAI
    model that accepts reasoning_effort (gpt-5 line, o-series, -pro) is
    treated as thinking. MiniMax M2.x always thinks (its <think> text bills
    as output). Unknown providers: False.
    """
    m = (model or "").strip().lower()
    p = provider or infer_provider(model)

    def openai_thinks(name: str) -> bool:
        if openai_is_classic_chat_model(name):
            return False
        return "-pro" in name or openai_reasoning_effort(name) is not None

    if p == "openai":
        return openai_thinks(m)
    if p == "openrouter":
        vendor, _, name = m.partition("/")
        if vendor == "openai":
            return openai_thinks(name.split(":", 1)[0])
        return openrouter_is_reasoning_model(model)
    if p == "anthropic":
        return anthropic_thinks_by_default(model)
    if p in ("gemini", "google"):
        return gemini_thinks_by_default(model)
    if p == "xai":
        return "reasoning" in m and "non-reasoning" not in m
    if p == "minimax":
        return True
    return False


def pro_reservation_estimate(
    *,
    deep_model: str,
    quick_model: str,
    auth_kind: str,
    provider: Optional[str] = None,
    selected_analysts: Optional[list[str]] = None,
    max_debate_rounds: int = 1,
    max_risk_discuss_rounds: int = 1,
) -> float:
    """Pre-run USD estimate for a Pro full-graph run (about 1.4x typical).

    Each node is priced at ITS model's rates (deep vs quick), resolved through
    `per_token_rates` so an unknown model gets a family ceiling, never $0.
    OAuth (ChatGPT subscription) and local runs return 0.0.
    """
    if auth_kind in ("oauth", "local"):
        return 0.0
    quick = quick_model or deep_model
    deep = deep_model or quick
    total = 0.0
    for b in pro_node_budgets(
        selected_analysts=selected_analysts,
        max_debate_rounds=max_debate_rounds,
        max_risk_discuss_rounds=max_risk_discuss_rounds,
    ):
        model = deep if b.tier == "deep" else quick
        rates = per_token_rates(model, provider)
        out_tokens: float = b.output_tokens
        if pro_model_reasons(model, provider):
            out_tokens *= PRO_REASONING_OUTPUT_FACTOR
        total += (b.input_tokens * rates["input"] + out_tokens * rates["output"]) / 1_000_000
    return total


def estimate_for_request(
    *,
    model: str,
    auth_kind: str,
    max_tokens: int,
    provider: Optional[str] = None,
    pro: Optional[dict] = None,
) -> float:
    """The ONE place a reserve/check request becomes a dollar estimate.

    Both /cost-guard endpoints and the WS auto-reserve go through reserve() /
    check(), which call this, so the same config always gives the same number.
    With a `pro` dict: the Pro full-graph estimator. Without: the
    simplified-debate worst case.
    """
    if pro is not None:
        inp = normalize_pro_fields(pro, fallback_model=model)
        return pro_reservation_estimate(
            deep_model=inp.deep_model,
            quick_model=inp.quick_model,
            auth_kind=auth_kind,
            provider=provider,
            selected_analysts=inp.selected_analysts,
            max_debate_rounds=inp.max_debate_rounds,
            max_risk_discuss_rounds=inp.max_risk_discuss_rounds,
        )
    return worst_case_reservation(
        model=model, auth_kind=auth_kind, max_tokens=max_tokens, provider=provider
    )


# ---- DB plumbing (delegates to storage._connect via a path lookup) --------
#
# We don't import _connect from storage.py to avoid coupling test setups; the
# DB path is the same. Tests can override TAL_SESSIONS_DB before initialize().


def _default_db_path() -> Path:
    override = os.environ.get("TAL_SESSIONS_DB")
    if override:
        return Path(override).expanduser().resolve()
    repo = Path.cwd()
    return (repo / "data" / "sessions.db").resolve()


_db_path: Path = _default_db_path()


def _reset_for_tests() -> None:
    """Test helper — re-resolve the path after a TAL_SESSIONS_DB change."""
    global _db_path
    _db_path = _default_db_path()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # Wait up to 5s for a competing writer instead of immediately raising
        # "database is locked". The bot and the WS handler can finalize spend
        # concurrently; without this a lock collision is swallowed by the
        # finalize except-block and silently understates the cost ledger.
        conn.execute("PRAGMA busy_timeout=5000")
        yield conn
    finally:
        conn.close()


def _new_reservation_id() -> str:
    """Same shape as storage._new_id — sortable + URL-safe."""
    ms = int(time.time() * 1000)
    rand = _secrets.token_hex(4)
    return f"{ms:012x}-{rand}"


# ---- Public API -------------------------------------------------------------


def initialize() -> None:
    """Create CostGuard tables, seed the config row, sweep stale reservations.

    Also ensures the parent `sessions` table exists by re-entering
    `storage._ensure_initialized()` (which sets `_initialized=True` before
    calling us, so the re-entry is a no-op).

    Idempotent. Called from `storage._ensure_initialized()` AND from every
    public CostGuard function so callers don't need to know the order.
    """
    # Ensure the sessions table exists before _compute_spend queries it.
    # storage sets `_initialized = True` before calling cost_guard.initialize,
    # so this re-entry is a cheap no-op when called from storage. When called
    # standalone (tests, direct API entry), this creates the sessions table.
    from . import storage as _storage

    _storage._ensure_initialized()
    _reset_for_tests()  # re-resolve path in case TAL_SESSIONS_DB changed
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(_SCHEMA_DDL)
        _add_missing_reservation_columns(conn)
        conn.execute(_SEED_CONFIG_SQL, (_iso(_utcnow()),))
        # Sweep any reservations that expired while the engine was down.
        _sweep_expired_reservations(conn)
        conn.commit()


def get_config() -> CostGuardConfig:
    initialize()
    with _connect() as conn:
        row = conn.execute(
            "SELECT enabled, cap_daily_usd, cap_weekly_usd, cap_monthly_usd, "
            "cap_sessions_per_day, updated_at FROM cost_guard_config WHERE id=1"
        ).fetchone()
    return _row_to_config(row)


def update_config(
    *,
    enabled: Optional[bool] = None,
    cap_daily_usd: Optional[float] = None,
    cap_weekly_usd: Optional[float] = None,
    cap_monthly_usd: Optional[float] = None,
    cap_sessions_per_day: Optional[int] = None,
) -> CostGuardConfig:
    """Patch the singleton config row. Only provided fields are updated."""
    initialize()
    current = get_config()
    new_enabled = current.enabled if enabled is None else bool(enabled)
    new_daily = current.cap_daily_usd if cap_daily_usd is None else max(0.0, float(cap_daily_usd))
    new_weekly = current.cap_weekly_usd if cap_weekly_usd is None else max(0.0, float(cap_weekly_usd))
    new_monthly = current.cap_monthly_usd if cap_monthly_usd is None else max(0.0, float(cap_monthly_usd))
    new_rate = current.cap_sessions_per_day if cap_sessions_per_day is None else max(0, int(cap_sessions_per_day))
    updated_at = _iso(_utcnow())
    with _connect() as conn:
        conn.execute(
            """
            UPDATE cost_guard_config
            SET enabled = ?, cap_daily_usd = ?, cap_weekly_usd = ?,
                cap_monthly_usd = ?, cap_sessions_per_day = ?, updated_at = ?
            WHERE id = 1
            """,
            (1 if new_enabled else 0, new_daily, new_weekly, new_monthly, new_rate, updated_at),
        )
        conn.commit()
    return CostGuardConfig(
        enabled=new_enabled,
        cap_daily_usd=new_daily,
        cap_weekly_usd=new_weekly,
        cap_monthly_usd=new_monthly,
        cap_sessions_per_day=new_rate,
        updated_at=updated_at,
    )


def get_state() -> tuple[SpendState, CostGuardConfig]:
    """Return current spend + config for renderer status displays."""
    initialize()
    config = get_config()
    with _connect() as conn:
        _sweep_expired_reservations(conn)
        spend = _compute_spend(conn)
        conn.commit()
    return spend, config


def check(
    *,
    model: str,
    auth_kind: str,
    max_tokens: int,
    provider: Optional[str] = None,
    pro: Optional[dict] = None,
) -> CheckResult:
    """Non-mutating preview: would this session be allowed under current caps?

    Computes the estimate (Pro full-graph estimate when `pro` is given, the
    simplified-debate worst case otherwise), reads current spend, returns
    allow/deny. Does NOT create a reservation. Safe for "preview" UI calls.
    """
    initialize()
    config = get_config()
    est = estimate_for_request(
        model=model, auth_kind=auth_kind, max_tokens=max_tokens, provider=provider, pro=pro
    )
    with _connect() as conn:
        _sweep_expired_reservations(conn)
        spend = _compute_spend(conn)
        conn.commit()
    if not config.enabled:
        return CheckResult(
            allow=True,
            over_dimension=None,
            override_available=True,
            current=spend,
            config=config,
            est_reservation_usd=est,
        )
    over = _exceeds_any_cap(spend=spend, config=config, est_cost=est, auth_kind=auth_kind)
    return CheckResult(
        allow=over is None,
        over_dimension=over,
        override_available=True,
        current=spend,
        config=config,
        est_reservation_usd=est,
    )


def reserve(
    *,
    model: str,
    auth_kind: str,
    max_tokens: int,
    override: bool = False,
    provider: Optional[str] = None,
    pro: Optional[dict] = None,
) -> ReserveResult:
    """Atomically check-and-insert a reservation row.

    Raises CostGuardBlocked if the caps would be exceeded and override=False.
    On success, the reservation_id must accompany the WS start frame and be
    finalized via `finalize_reservation()` when the debate ends.

    With `pro` (a Pro full-graph run): the Pro estimate, the 60-minute TTL,
    and a mid-run USD limit stored on the row for `run_usd_limit()`.
    """
    initialize()
    config = get_config()
    est = estimate_for_request(
        model=model, auth_kind=auth_kind, max_tokens=max_tokens, provider=provider, pro=pro
    )
    rid = _new_reservation_id()
    now = _utcnow()
    ttl = PRO_RESERVATION_TTL_SECONDS if pro is not None else RESERVATION_TTL_SECONDS
    expires = now + timedelta(seconds=ttl)
    with _connect() as conn:
        # Single transaction: sweep, check, insert.
        _sweep_expired_reservations(conn)
        spend = _compute_spend(conn)
        if config.enabled and not override:
            over = _exceeds_any_cap(spend=spend, config=config, est_cost=est, auth_kind=auth_kind)
            if over is not None:
                conn.rollback()
                raise CostGuardBlocked(
                    over_dimension=over,
                    spend=spend,
                    config=config,
                    est_cost=est,
                )
        # `spend` was read BEFORE this row exists, so it is exactly "spend plus
        # other live reservations", which is what the headroom rule needs.
        limit, reason, dimension = _run_limit(
            spend=spend, config=config, est_cost=est, auth_kind=auth_kind, override=override
        )
        conn.execute(
            """
            INSERT INTO cost_reservations (
                id, created_at, expires_at, est_cost_usd, auth_kind,
                override, finalized, finalized_cost_usd,
                usd_limit, limit_reason, limit_dimension
            ) VALUES (?, ?, ?, ?, ?, ?, 0, NULL, ?, ?, ?)
            """,
            (rid, _iso(now), _iso(expires), est, auth_kind, 1 if override else 0,
             limit, reason, dimension),
        )
        conn.commit()
    return ReserveResult(
        reservation_id=rid,
        est_cost_usd=est,
        expires_at=_iso(expires),
        auth_kind=auth_kind,
        override=override,
        usd_limit=limit,
        limit_reason=reason,
        limit_dimension=dimension,
    )


def run_usd_limit(reservation_id: Optional[str]) -> Optional[RunLimit]:
    """The mid-run USD limit stored on a reservation, or None for no USD stop.

    None when: no reservation id, an unknown id, or an OAuth/local run (they
    cost $0; only the optional token cap applies). Best-effort: a DB error
    also returns None, and the pre-run reservation still stands.
    """
    if not reservation_id:
        return None
    try:
        initialize()
        with _connect() as conn:
            row = conn.execute(
                "SELECT est_cost_usd, usd_limit, limit_reason, limit_dimension "
                "FROM cost_reservations WHERE id = ?",
                (reservation_id,),
            ).fetchone()
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[cost_guard] run_usd_limit failed for {reservation_id}: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return None
    if row is None or row["usd_limit"] is None:
        return None
    return RunLimit(
        limit_usd=float(row["usd_limit"]),
        reason=str(row["limit_reason"] or "runaway"),
        dimension=row["limit_dimension"],
        est_cost_usd=float(row["est_cost_usd"]),
    )


def refresh_run_limit(
    reservation_id: Optional[str],
    *,
    spent_usd: float,
    next_call_usd: float,
) -> Optional[float]:
    """Keep a running Pro reservation honest while it runs; return its
    current USD limit (None: leave the limit unchanged).

    Called by the Pro engine after each graph node. Two jobs:

    1. Raise this reservation's `est_cost_usd` to at least what the run has
       already spent plus one more call. Without this, a second run started
       meanwhile sees only our pre-run estimate and could take headroom we
       are already using (two runs could then overshoot a cap together).
    2. For a "cap" reservation, recompute the headroom LIVE: the smallest
       (cap - spend of everything else) across enabled USD caps. Another run
       that started or finished since our reserve changes our room. Runaway
       limits (override, caps off) are fixed and returned unchanged.

    Granularity is one node: calls inside a node (an analyst's tool loop)
    use the limit from the last refresh. Best-effort: on any DB error the
    caller keeps its current limit.
    """
    if not reservation_id:
        return None
    try:
        initialize()
        with _connect() as conn:
            conn.execute(
                """
                UPDATE cost_reservations
                SET est_cost_usd = MAX(est_cost_usd, ?)
                WHERE id = ? AND finalized = 0
                """,
                (max(0.0, float(spent_usd) + float(next_call_usd)), reservation_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT est_cost_usd, usd_limit, limit_reason, finalized, expires_at "
                "FROM cost_reservations WHERE id = ?",
                (reservation_id,),
            ).fetchone()
            if row is None or row["usd_limit"] is None:
                return None
            if str(row["limit_reason"] or "") != "cap":
                return float(row["usd_limit"])
            config = _row_to_config(
                conn.execute("SELECT * FROM cost_guard_config WHERE id = 1").fetchone()
            )
            spend = _compute_spend(conn)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[cost_guard] refresh_run_limit failed for {reservation_id}: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return None
    # `spend` counts our own live reservation; take it out so the result is
    # the room left for THIS run. (A swept or finalized row is not in spend.)
    own = (
        float(row["est_cost_usd"])
        if not row["finalized"] and str(row["expires_at"]) > _iso(_utcnow())
        else 0.0
    )
    headrooms = [
        cap - (used - own)
        for cap, used in (
            (config.cap_daily_usd, spend.daily_usd),
            (config.cap_weekly_usd, spend.weekly_usd),
            (config.cap_monthly_usd, spend.monthly_usd),
        )
        if cap > 0
    ]
    if not config.enabled or not headrooms:
        # Caps were switched off mid-run: keep the limit set at reserve time.
        return float(row["usd_limit"])
    return max(0.0, min(headrooms))


def mark_unrecorded(reservation_id: Optional[str]) -> bool:
    """Flag a finalized reservation as carrying the run's only cost record.

    Used when a run completed but its sessions row could not be written:
    without this the reservation (finalized as recorded) and the missing row
    would together count the paid run as $0 against every cap.
    """
    if not reservation_id:
        return False
    try:
        initialize()
        with _connect() as conn:
            cur = conn.execute(
                "UPDATE cost_reservations SET unrecorded = 1 WHERE id = ?",
                (reservation_id,),
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[cost_guard] mark_unrecorded failed for {reservation_id}: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return False


def finalize_reservation(
    reservation_id: str,
    *,
    actual_cost_usd: float,
    unrecorded: bool = False,
) -> bool:
    """Mark a reservation as finalized with the real cost.

    `unrecorded=True` means "no session row will carry this cost" (an aborted
    run: token cap, cost cap, node error, disconnect). The finalized cost then
    counts toward the caps by itself (see `_compute_spend`). A completed run
    passes False because its `sessions` row already carries the cost.

    Idempotent: only a row whose cost is still unset is updated, so a second
    call is a no-op. That condition (rather than `finalized = 0`) also lets a
    run that outlived its TTL, and was swept to finalized with no cost, still
    record what it really spent. Returns True if a row was updated, False if
    the reservation_id was unknown or already settled (logged, not raised, so
    the debate's finally block is robust to weird states).
    """
    if not reservation_id:
        return False
    try:
        initialize()
        with _connect() as conn:
            cur = conn.execute(
                """
                UPDATE cost_reservations
                SET finalized = 1, finalized_cost_usd = ?, unrecorded = ?
                WHERE id = ? AND finalized_cost_usd IS NULL
                """,
                (max(0.0, float(actual_cost_usd)), 1 if unrecorded else 0, reservation_id),
            )
            conn.commit()
            return cur.rowcount > 0
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[cost_guard] finalize failed for {reservation_id}: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return False


# ---- Internals --------------------------------------------------------------


def _add_missing_reservation_columns(conn: sqlite3.Connection) -> None:
    """Additive migration for databases created before these columns existed."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(cost_reservations)").fetchall()}
    for name, decl in _RESERVATION_ADDED_COLUMNS:
        if name not in have:
            try:
                conn.execute(f"ALTER TABLE cost_reservations ADD COLUMN {name} {decl}")
            except sqlite3.OperationalError as exc:
                # Two threads migrating the same old database at once: the
                # loser sees "duplicate column", which means the work is done.
                if "duplicate column" not in str(exc).lower():
                    raise


def _run_limit(
    *,
    spend: SpendState,
    config: CostGuardConfig,
    est_cost: float,
    auth_kind: str,
    override: bool,
) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """(limit_usd, reason, dimension) for a new reservation (founder rule,
    2026-11-14). `spend` must EXCLUDE this reservation.

    - OAuth / local: (None, None, None). They cost $0; no USD stop.
    - Normal run: the smallest headroom across enabled USD caps, where
      headroom = cap - (spend + other live reservations). Equivalently
      cap - total_including_this_reservation + this_estimate. The run is
      stopped only if continuing would push spend past a cap; overshooting
      its own estimate while under the cap is fine.
    - Override run, Cost Guard disabled, or no USD cap enabled: no cap stop,
      but a runaway stop at RUNAWAY_MULTIPLIER x the estimate.
    """
    if auth_kind in ("oauth", "local"):
        return None, None, None
    if config.enabled and not override:
        candidates = [
            (config.cap_daily_usd - spend.daily_usd, "daily", config.cap_daily_usd),
            (config.cap_weekly_usd - spend.weekly_usd, "weekly", config.cap_weekly_usd),
            (config.cap_monthly_usd - spend.monthly_usd, "monthly", config.cap_monthly_usd),
        ]
        enabled = [(h, d) for (h, d, cap) in candidates if cap > 0]
        if enabled:
            headroom, dimension = min(enabled, key=lambda x: x[0])
            return max(0.0, headroom), "cap", dimension
    return est_cost * RUNAWAY_MULTIPLIER, "runaway", None


def _row_to_config(row: sqlite3.Row) -> CostGuardConfig:
    return CostGuardConfig(
        enabled=bool(row["enabled"]),
        cap_daily_usd=float(row["cap_daily_usd"]),
        cap_weekly_usd=float(row["cap_weekly_usd"]),
        cap_monthly_usd=float(row["cap_monthly_usd"]),
        cap_sessions_per_day=int(row["cap_sessions_per_day"]),
        updated_at=str(row["updated_at"]),
    )


def _sweep_expired_reservations(conn: sqlite3.Connection) -> int:
    """Mark reservations finalized whose expires_at is in the past.

    Returns the number of swept rows. Caller is responsible for commit.
    """
    cur = conn.execute(
        "UPDATE cost_reservations SET finalized = 1 "
        "WHERE finalized = 0 AND expires_at < ?",
        (_iso(_utcnow()),),
    )
    return cur.rowcount


def _compute_spend(conn: sqlite3.Connection) -> SpendState:
    """Aggregate completed-session cost + active-reservation cost + the real
    cost of aborted runs (finalized with `unrecorded=1`) per window.

    OAuth sessions are excluded from the cost sums (they're $0). Session
    counts include all live sessions regardless of auth_kind so the rate
    cap covers OAuth quota.
    """
    now = _iso(_utcnow())
    day_start = _window_start("day")
    week_start = _window_start("week")
    month_start = _window_start("month")

    def cost_sum(since: str) -> float:
        # Older sessions may have NULL auth_kind (predates the column). Treat
        # NULL as api_key — they recorded a non-zero estimated_cost_usd, so
        # they were definitely API-tier billing. The ledger remains coherent.
        row = conn.execute(
            """
            SELECT COALESCE(SUM(estimated_cost_usd), 0)
            FROM sessions
            WHERE live = 1
              AND estimated_cost_usd IS NOT NULL
              AND (auth_kind IS NULL OR auth_kind = 'api_key')
              AND created_at >= ?
            """,
            (since,),
        ).fetchone()
        return float(row[0])

    def reserved_cost(since: str) -> float:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(est_cost_usd), 0)
            FROM cost_reservations
            WHERE finalized = 0
              AND expires_at > ?
              AND auth_kind = 'api_key'
              AND created_at >= ?
            """,
            (now, since),
        ).fetchone()
        return float(row[0])

    def aborted_cost(since: str) -> float:
        # Aborted runs write no sessions row, so their real (partial) cost
        # lives only on the finalized reservation. Without this sum a run
        # stopped by a cap, an error or a disconnect would be free.
        row = conn.execute(
            """
            SELECT COALESCE(SUM(finalized_cost_usd), 0)
            FROM cost_reservations
            WHERE finalized = 1
              AND unrecorded = 1
              AND finalized_cost_usd IS NOT NULL
              AND auth_kind = 'api_key'
              AND created_at >= ?
            """,
            (since,),
        ).fetchone()
        return float(row[0])

    def usd(since: str) -> float:
        return round(cost_sum(since) + reserved_cost(since) + aborted_cost(since), 6)

    def session_count(since: str) -> int:
        row = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE live = 1 AND created_at >= ?",
            (since,),
        ).fetchone()
        return int(row[0])

    def reserved_count(since: str) -> int:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM cost_reservations
            WHERE finalized = 0 AND expires_at > ? AND created_at >= ?
            """,
            (now, since),
        ).fetchone()
        return int(row[0])

    return SpendState(
        daily_usd=usd(day_start),
        weekly_usd=usd(week_start),
        monthly_usd=usd(month_start),
        sessions_today=session_count(day_start) + reserved_count(day_start),
    )


def _exceeds_any_cap(
    *,
    spend: SpendState,
    config: CostGuardConfig,
    est_cost: float,
    auth_kind: str,
) -> Optional[str]:
    """Return the first cap dimension exceeded by adding `est_cost` to spend.

    OAuth and local sessions skip the three USD caps (cost is $0) but still
    hit the rate cap — even free LLM runs benefit from quota discipline on
    runaway debate counts. A USD cap of 0 means "disabled" (skipped), per
    UI convention. Same for sessions_per_day = 0.
    """
    if auth_kind not in ("oauth", "local"):
        if config.cap_daily_usd > 0 and spend.daily_usd + est_cost > config.cap_daily_usd:
            return "daily"
        if config.cap_weekly_usd > 0 and spend.weekly_usd + est_cost > config.cap_weekly_usd:
            return "weekly"
        if config.cap_monthly_usd > 0 and spend.monthly_usd + est_cost > config.cap_monthly_usd:
            return "monthly"
    if config.cap_sessions_per_day > 0 and spend.sessions_today + 1 > config.cap_sessions_per_day:
        return "rate"
    return None


# ---- Errors -----------------------------------------------------------------


class CostGuardBlocked(RuntimeError):
    """Raised by reserve() when caps would be exceeded and override=False."""

    def __init__(
        self,
        *,
        over_dimension: str,
        spend: SpendState,
        config: CostGuardConfig,
        est_cost: float,
    ) -> None:
        self.over_dimension = over_dimension
        self.spend = spend
        self.config = config
        self.est_cost = est_cost
        super().__init__(
            f"cost guard blocked: would exceed {over_dimension} cap "
            f"(est_cost={est_cost:.4f})"
        )


# ---- Serialization helpers --------------------------------------------------


def config_to_dict(c: CostGuardConfig) -> dict[str, Any]:
    return asdict(c)


def spend_to_dict(s: SpendState) -> dict[str, Any]:
    return asdict(s)


def check_result_to_dict(r: CheckResult) -> dict[str, Any]:
    return {
        "allow": r.allow,
        "over_dimension": r.over_dimension,
        "override_available": r.override_available,
        "current": spend_to_dict(r.current),
        "config": config_to_dict(r.config),
        "est_reservation_usd": round(r.est_reservation_usd, 6),
    }


def reserve_result_to_dict(r: ReserveResult) -> dict[str, Any]:
    return {
        "reservation_id": r.reservation_id,
        "est_cost_usd": round(r.est_cost_usd, 6),
        "expires_at": r.expires_at,
        "auth_kind": r.auth_kind,
        "override": r.override,
        "usd_limit": None if r.usd_limit is None else round(r.usd_limit, 6),
        "limit_reason": r.limit_reason,
        "limit_dimension": r.limit_dimension,
    }


__all__ = [
    "CostGuardBlocked",
    "CostGuardConfig",
    "SpendState",
    "CheckResult",
    "ReserveResult",
    "RunLimit",
    "NodeBudget",
    "ProEstimateInputs",
    "RESERVATION_TTL_SECONDS",
    "PRO_RESERVATION_TTL_SECONDS",
    "RUNAWAY_MULTIPLIER",
    "PRO_ESTIMATE_FACTOR",
    "PRO_REASONING_OUTPUT_FACTOR",
    "initialize",
    "get_config",
    "update_config",
    "get_state",
    "check",
    "reserve",
    "finalize_reservation",
    "run_usd_limit",
    "worst_case_reservation",
    "pro_reservation_estimate",
    "pro_node_budgets",
    "pro_model_reasons",
    "normalize_pro_fields",
    "estimate_for_request",
    "config_to_dict",
    "spend_to_dict",
    "check_result_to_dict",
    "reserve_result_to_dict",
]
