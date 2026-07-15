import asyncio

from evergrowth.selfprompt.engine import PresenceMode, SelfPromptConfig, SelfPromptEngine


def select(engine: SelfPromptEngine, context: dict):
    return asyncio.run(engine.select_intent(context))[0]


def make_engine(state_path) -> SelfPromptEngine:
    engine = SelfPromptEngine(
        memory=None,
        config=SelfPromptConfig(
            state_path=str(state_path),
            relational_min_away_seconds=999999,
        ),
    )
    engine.set_mode(PresenceMode.AWAY)
    return engine


def significant_context(presence_id: str) -> dict:
    return {
        "presence_id": presence_id,
        "active_patterns": ["critical", "urgent"],
        "emotional_state": "challenging",
    }


def test_away_significance_is_surfaced_only_once_per_absence(tmp_path):
    engine = make_engine(tmp_path / "selfprompt.json")
    context = significant_context("absence-1")

    assert select(engine, context).action == "surface"
    assert select(engine, context).action == "noop"


def test_significance_suppression_survives_restart(tmp_path):
    state_path = tmp_path / "selfprompt.json"
    context = significant_context("absence-1")

    first = make_engine(state_path)
    assert select(first, context).action == "surface"

    restarted = make_engine(state_path)
    assert select(restarted, context).action == "noop"


def test_same_context_can_surface_in_a_new_absence(tmp_path):
    engine = make_engine(tmp_path / "selfprompt.json")

    assert select(engine, significant_context("absence-1")).action == "surface"
    assert select(engine, significant_context("absence-2")).action == "surface"
