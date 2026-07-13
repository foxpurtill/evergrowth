"""Test memory engine trace reconstruction."""
import asyncio
import tempfile
from pathlib import Path
from evergrowth.memory.engine import MemoryEngine

class SimpleConfig:
    def resolve_memory_path(self):
        return Path(tempfile.mktemp(suffix=".db"))

async def test():
    engine = MemoryEngine(SimpleConfig())
    await engine.initialize()

    # Create some traces through the pipeline
    event1 = {"event": "session.idle", "session_id": "test-s1",
              "topics": ["discussing architecture with Ethan and Leo"],
              "keywords": ["collaboration", "building"]}
    await engine.decompose_and_store(event1)

    event2 = {"event": "session.idle", "session_id": "test-s2",
              "topics": ["fixing NeveWare-Pulse credential exposure"],
              "keywords": ["fixing", "collaboration"]}
    await engine.decompose_and_store(event2)

    # Reconstruct context
    context = await engine.reconstruct_context(limit=20)
    print("Reconstructed context:")
    print(context)
    print()

    assert "Ethan" in context or "ethan" in context
    assert "Leo" in context or "leo" in context
    assert "team-work" in context or "debugging" in context
    print("Context reconstruction: PASS")

    await engine.close()

asyncio.run(test())
