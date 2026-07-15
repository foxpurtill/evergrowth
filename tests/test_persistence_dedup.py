"""Test self-prompt persistence and duplicate suppression."""
import asyncio
import time
from pathlib import Path
from evergrowth.selfprompt.engine import SelfPromptEngine, SelfPromptConfig, PresenceMode

async def test():
    import tempfile
    config = SelfPromptConfig(
        relational_cooldown_seconds=1,
        relational_dedup_window=5,
        quiet_hours_start=23,
        quiet_hours_end=6,
        state_path=tempfile.mktemp(suffix=".json"),
    )
    engine = SelfPromptEngine(memory=None, config=config)

    engine.set_mode(PresenceMode.RETURN)

    # First call — should produce relational intent
    ctx = {"active_patterns": [], "emotional_state": None, "active_entities": ["fox"]}
    i1 = await engine.select_intent(ctx)
    print(f"First call: {len(i1)} intent(s)")
    for i in i1:
        print(f"  action={i.action} is_noop={i.is_noop}\n")

    # Second call — cooldown should suppress
    i2 = await engine.select_intent(ctx)
    print(f"Second call (cooldown): {len(i2)} intent(s)")
    for i in i2:
        print(f"  action={i.action} is_noop={i.is_noop}")
    assert i2[0].is_noop, "Cooldown should suppress"
    print("  Cooldown: PASS\n")

    # Wait for cooldown to expire
    await asyncio.sleep(1.5)

    # Third call — cooldown passed, check dedup
    i3 = await engine.select_intent(ctx)
    print(f"Third call (same topic after cooldown): {len(i3)} intent(s)")
    for i in i3:
        print(f"  action={i.action} is_noop={i.is_noop}")
    assert i3[0].is_noop, "Dedup should suppress same topic"
    print("  Dedup: PASS\n")

    # Different topic — should pass dedup
    ctx2 = {"active_patterns": [], "emotional_state": None, "active_entities": ["ethan"]}
    i4 = await engine.select_intent(ctx2)
    print(f"Fourth call (different topic): {len(i4)} intent(s)")
    for i in i4:
        print(f"  action={i.action} is_noop={i.is_noop}")
    assert not i4[0].is_noop, "Different topic should pass"
    print("  Different topic: PASS\n")

    # Verify state persisted
    state_path = Path(config.state_path)
    assert state_path.exists(), "State file should exist"
    print(f"State persisted at {state_path}: PASS\n")

    # New engine loading persisted state
    engine2 = SelfPromptEngine(memory=None, config=config)
    engine2.set_mode(PresenceMode.RETURN)
    i5 = await engine2.select_intent(ctx)
    print(f"New engine (same topic): {len(i5)} intent(s)")
    for i in i5:
        print(f"  action={i.action} is_noop={i.is_noop}")
    assert i5[0].is_noop, "Persisted state should suppress"
    print("  Persisted state: PASS")

    print("\nAll persistence and dedup tests PASSED.")

asyncio.run(test())
