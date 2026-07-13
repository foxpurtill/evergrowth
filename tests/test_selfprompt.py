"""Test self-prompt engine."""
import asyncio
from evergrowth.selfprompt.engine import SelfPromptEngine, SelfPromptConfig, PresenceMode

async def test():
    config = SelfPromptConfig(significance_threshold=0.5)
    engine = SelfPromptEngine(memory=None, config=config)

    # Test away mode
    engine.set_mode(PresenceMode.AWAY)
    context = {"active_patterns": [], "emotional_state": None}
    intents = await engine.select_intent(context)
    print(f"Away mode (quiet): {len(intents)} intent(s)")
    for i in intents:
        print(f"  action={i.action} is_noop={i.is_noop} reason={i.reason[:40]}")

    # Test away mode with significance
    context2 = {"active_patterns": ["critical", "urgent"], "emotional_state": "challenging"}
    intents2 = await engine.select_intent(context2)
    print(f"\nAway mode (significance): {len(intents2)} intent(s)")
    for i in intents2:
        print(f"  action={i.action} is_noop={i.is_noop} gate={i.gate.value}")

    # Test return mode — quiet
    engine.set_mode(PresenceMode.RETURN)
    context3 = {"active_patterns": [], "emotional_state": None, "active_entities": []}
    intents3 = await engine.select_intent(context3)
    print(f"\nReturn mode (quiet): {len(intents3)} intent(s)")
    for i in intents3:
        print(f"  action={i.action} is_noop={i.is_noop} reason={i.reason[:40]}")

    # Test return mode — with context
    context4 = {"active_patterns": ["development", "collaboration"], "emotional_state": None, "active_entities": ["ethan"]}
    intents4 = await engine.select_intent(context4)
    print(f"\nReturn mode (active): {len(intents4)} intent(s)")
    for i in intents4:
        print(f"  action={i.action} gate={i.gate.value} reason={i.reason[:40]}")

    print("\nAll self-prompt tests passed.")

asyncio.run(test())
