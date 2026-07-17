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
    assert intents[0].action == "research"
    assert intents[0].is_noop is False


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
    assert second[0].action == "research"

    restarted = make_engine(tmp_path)
    third = run(restarted.select_intent(context))
    assert third[0].action == "research"


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


def test_new_absence_ignores_cross_topic_dedup(tmp_path):
    engine = make_engine(tmp_path)
    engine._last_relational_time = 1000.0
    engine._last_relational_topic = "general"
    engine._save_state()

    import evergrowth.selfprompt.engine as module
    original = module.time.time
    module.time.time = lambda: 1401.0
    try:
        intents = run(engine.select_intent({
            "presence_id": "new-absence",
            "elapsed_seconds": 1900,
            "relational_outreach_allowed": True,
            "active_patterns": ["one", "two"],
        }))
    finally:
        module.time.time = original

    assert intents[0].action == "check_in"


def test_failed_delivery_releases_presence_id_for_retry(tmp_path):
    engine = make_engine(tmp_path)
    context = {
        "presence_id": "p-retry", "elapsed_seconds": 1900,
        "relational_outreach_allowed": True,
    }
    first = run(engine.select_intent(context))
    assert first[0].action == "check_in"

    result = engine.record_relational_delivery("p-retry", delivered=False)
    assert result["status"] == "released"

    second = run(engine.select_intent(context))
    assert second[0].action == "check_in"


def test_confirmed_delivery_commits_dedup_and_cooldown(tmp_path):
    engine = make_engine(tmp_path)
    context = {
        "presence_id": "p-confirmed", "elapsed_seconds": 1900,
        "relational_outreach_allowed": True,
    }
    run(engine.select_intent(context))
    before = engine._last_relational_time
    result = engine.record_relational_delivery("p-confirmed", delivered=True)

    assert result["status"] == "confirmed"
    assert "p-confirmed" in engine._relational_presence_ids
    assert engine._last_relational_time >= before
    assert run(engine.select_intent(context))[0].action == "research"

def test_stale_reservation_expires_and_retries(tmp_path, monkeypatch):
    engine = make_engine(tmp_path, outreach_reservation_ttl_seconds=10)
    context = {
        "presence_id": "p-expired", "elapsed_seconds": 1900,
        "relational_outreach_allowed": True,
    }
    import evergrowth.selfprompt.engine as module
    monkeypatch.setattr(module.time, "time", lambda: 100.0)
    assert run(engine.select_intent(context))[0].action == "check_in"

    monkeypatch.setattr(module.time, "time", lambda: 111.0)
    assert run(engine.select_intent(context))[0].action == "check_in"


def test_away_quiet_hours_suppress_outreach_not_internal_work(tmp_path):
    config = SelfPromptConfig(
        state_path=str(tmp_path / "selfprompt_state.json"),
        relational_min_away_seconds=0,
        relational_cooldown_seconds=0,
        quiet_hours_start=0,
        quiet_hours_end=24,
    )
    engine = SelfPromptEngine(memory=None, config=config)
    engine.set_mode(PresenceMode.AWAY)

    intents = run(engine.select_intent({
        "presence_id": "overnight",
        "elapsed_seconds": 3600,
        "relational_outreach_allowed": True,
    }))

    assert intents[0].action == "research"
    assert intents[0].is_noop is False
