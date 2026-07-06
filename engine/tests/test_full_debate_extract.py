"""Transcript extraction for the full graph — regression coverage.

The risk debate keeps a SEPARATE current_*_response field per speaker in
risk_debate_state, and every node re-emits the whole state. A first-non-empty
scan returned the aggressive analyst's line for the conservative / neutral /
PM turns (founder-visible transcript bug, 2026-07-05). Extraction must be
keyed by the node that spoke.

Requires the Pro venv (full_debate imports the tradingagents library).
"""

import pytest

pytest.importorskip("tradingagents")

from engine.full_debate import _extract_content  # noqa: E402


def _risk_delta() -> dict:
    """A late-round risk delta: every speaker's field is populated, exactly
    the state shape that used to trip the first-non-empty scan."""
    return {
        "risk_debate_state": {
            "current_aggressive_response": "AGG line",
            "current_conservative_response": "CON line",
            "current_neutral_response": "NEU line",
            "judge_decision": "PM decision",
            "latest_speaker": "Neutral Analyst",
        }
    }


def test_risk_extraction_is_keyed_by_speaker():
    delta = _risk_delta()
    assert _extract_content("Aggressive Analyst", delta, "risk") == "AGG line"
    assert _extract_content("Conservative Analyst", delta, "risk") == "CON line"
    assert _extract_content("Neutral Analyst", delta, "risk") == "NEU line"


def test_pm_extraction_prefers_judge_decision():
    assert (
        _extract_content("Portfolio Manager", _risk_delta(), "risk")
        == "PM decision"
    )


def test_risk_node_missing_own_line_falls_through_to_messages():
    """A risk node with no own-line yet must NOT pick up another speaker's
    text — it falls through to the last-message fallback (empty here)."""
    delta = {
        "risk_debate_state": {
            "current_aggressive_response": "AGG line",
        }
    }
    assert _extract_content("Conservative Analyst", delta, "risk") == ""


def test_researcher_extraction_unchanged():
    """The researcher loop shares ONE current_response field (each speaker
    overwrites it), so the existing scan is correct there — pin it."""
    delta = {"investment_debate_state": {"current_response": "BULL line"}}
    assert _extract_content("Bull Researcher", delta, "researchers") == "BULL line"
