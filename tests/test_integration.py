"""Test trace integration with memory engine."""
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

    event = {
        "event": "session.idle",
        "session_id": "integration-test-1",
        "topics": ["discussing architecture with Ethan and Leo", "planning trace schema"],
        "keywords": ["collaboration", "building"],
        "dedup_key": "session.idle:test-123:msg1:msg5",
    }

    # First pass: should produce 4 traces
    traces = await engine.decompose_and_store(event)
    print(f"Stored {len(traces)} traces")

    for t in traces:
        print(f"  [{t['trace_type']:12}] decay={t['decay_curve']} dedup={t['dedup_key'][:12]}")

    # Retrieve by session
    retrieved = await engine.get_traces_by_session("integration-test-1")
    print(f"\nRetrieved {len(retrieved)} traces for session (expected 4)")

    # Dedup test: same event again should produce 0 new traces
    traces2 = await engine.decompose_and_store(event)
    print(f"Dedup: got {len(traces2)} new traces (expected 0)")

    if len(retrieved) == 4 and len(traces2) == 0:
        print("\nIntegration: PASS")
    else:
        print("\nIntegration: FAIL")

    await engine.close()

asyncio.run(test())
