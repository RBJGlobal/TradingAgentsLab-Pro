"""_parse_pm_decision: 5-tier rating -> stance mapping (presentation layer).

The upstream Portfolio Manager's markdown carries a Buy/Overweight/Hold/
Underweight/Sell rating. The app's own surfaces never repeat that directive:
the parser maps it onto the analytical stance vocabulary. These tests pin
the mapping and the fallback so a drift in either silently reintroducing a
trade-directive field would fail loudly.
"""
from engine.full_debate import _parse_pm_decision


def _state(text: str) -> dict:
    return {"final_trade_decision": text}


def _pm(rating: str) -> str:
    return (
        f"**Rating**: {rating}\n"
        "**Executive Summary**: Balanced setup with mild edge.\n"
        "**Investment Thesis**: Long-term platform strength.\n"
        "**Price Target**: 337.50\n"
        "**Time Horizon**: 3-6 months\n"
    )


def test_five_tier_rating_maps_to_stances():
    expected = {
        "Buy": ("bullish", 0.85),
        "Overweight": ("moderately_bullish", 0.65),
        "Hold": ("neutral", 0.5),
        "Underweight": ("moderately_bearish", 0.65),
        "Sell": ("bearish", 0.85),
    }
    for rating, (stance, conviction) in expected.items():
        d = _parse_pm_decision(_state(_pm(rating)))
        assert d["stance"] == stance, rating
        assert d["conviction"] == conviction, rating


def test_no_trade_directive_fields_in_decision():
    d = _parse_pm_decision(_state(_pm("Sell")))
    assert "action" not in d
    assert "rating" not in d
    assert "confidence" not in d


def test_rich_fields_still_parsed():
    d = _parse_pm_decision(_state(_pm("Overweight")))
    assert d["price_target"] == 337.50
    assert d["time_horizon"] == "3-6 months"
    assert d["investment_thesis"].startswith("Long-term")
    assert d["reasoning"].startswith("Balanced setup")


def test_missing_rating_falls_back_neutral():
    d = _parse_pm_decision(_state("Some unstructured verdict text."))
    assert d["stance"] == "neutral"
    assert d["conviction"] == 0.5
    assert d["reasoning"] == "Some unstructured verdict text."


def test_empty_state_falls_back_neutral():
    d = _parse_pm_decision(None)
    assert d["stance"] == "neutral"
    assert d["reasoning"] == "No assessment text produced."
