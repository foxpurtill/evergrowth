import asyncio

from evergrowth.selfprompt.engine import PresenceMode, SelfPromptConfig, SelfPromptEngine


def run(coro):
    return asyncio.run(coro)


def make_engine(tmp_path, **overrides):
    config = SelfPromptConfig(
        state_path=str(tmp_path / "selfprompt_state.json"),
        relational_min_away_seconds=1800,
        relational_cooldown_seconds=0,
        quiet_hours_start=24,
        quiet_hours_end=0,
        **overrides,
    )
    engine = SelfPromptEngine(memory=None, config=config)
    engine.set_mode(PresenceMode.AWAY)
    return engine


def test_away_relational_waits_until_absence_is_established(tmp_path):
    engine = make_engine(tmp_path)
    intents = run(engine.select_intent({
        "presence_id": "p1", "elapsed_seconds": 1799,
        "relational_outreach_allowed": True,
    }))
    assert intents[0].is_noop


def test_away_relational_sends_once_per_presence_id_and_persists(tmp_path):
    engine = make_engine(tmp_path)
    context = {
        "presence_id": "p2", "elapsed_seconds": 1900,
        "relational_outreach_allowed": True,
    }
    first = run(engine.select_intent(context))
    assert first[0].action == "check_in"
    assert first[0].presence_id == "p2"

    second = run(engine.select_intent(context))
    assert second[0].is_noop

    restarted = make_engine(tmp_path)
    third = run(restarted.select_intent(context))
    assert third[0].is_noop


def test_away_relational_is_not_starved_by_significance(tmp_path):
    engine = make_engine(tmp_path)
    intents = run(engine.select_intent({
        "presence_id": "p-significant",
        "elapsed_seconds": 1900,
        "relational_outreach_allowed": True,
        "active_patterns": ["one", "two"],
    }))

    assert intents[0].action == "check_in"
    assert intents[0].gate.value == "relational"


def test_return_cancels_pending_without_fabricating_new_cooldown(tmp_path):
    engine = make_engine(tmp_path)
    before = engine._last_relational_time
    engine.set_mode(PresenceMode.RETURN, "p3")
    assert engine._pending_relational is False
    assert engine._last_relational_time == before
