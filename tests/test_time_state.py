"""Tests for dynamic time-state scoring."""

from evergrowth.memory.time_state import TimeStateScorer


def trace(**overrides):
    base = {
        "trace_type": "episodic",
        "created_at": 1_000_000.0,
        "decay_curve": "fast",
        "significance": 0.0,
        "summary": "ordinary session event",
        "source_session_id": "session-a",
        "pattern_id": None,
        "emotional_valence": None,
    }
    base.update(overrides)
    return base


def test_recent_trace_outranks_old_equivalent():
    scorer = TimeStateScorer()
    ranked = scorer.score_many([
        trace(summary="old", created_at=1_000_000.0),
        trace(summary="new", created_at=1_259_100.0),
    ], now=1_259_200.0)
    assert ranked[0]["summary"] == "new"
    assert ranked[0]["time_state"]["band"] == "just_now"


def test_unresolved_and_emotional_boosts_are_visible():
    scorer = TimeStateScorer()
    ranked = scorer.score_many([
        trace(summary="ordinary"),
        trace(summary="urgent blocked next step", emotional_valence=-1.0),
    ], now=1_000_100.0)
    boosted = ranked[0]["time_state"]
    assert boosted["emotional_boost"] > 0
    assert boosted["unresolved_boost"] == 0.18


def test_recurrence_boosts_shared_pattern():
    scorer = TimeStateScorer()
    ranked = scorer.score_many([
        trace(summary="one", pattern_id="debugging"),
        trace(summary="two", pattern_id="debugging"),
        trace(summary="solo", pattern_id="research"),
    ], now=1_000_100.0)
    debugging = [x for x in ranked if x["pattern_id"] == "debugging"]
    assert all(x["time_state"]["recurrence_boost"] > 0 for x in debugging)
