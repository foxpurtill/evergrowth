"""Test the trace classification engine."""
from evergrowth.memory.traces import FiveTraceDecomposer

decomposer = FiveTraceDecomposer()

# Simulate a capture event from Leo's payload shape
event = {
    "event": "session.idle",
    "session_id": "test-123",
    "topic": "discussing architecture with Ethan and Leo",
    "topics": ["discussing architecture with Ethan and Leo", "deciding on trace schema"],
    "keywords": ["collaboration", "building"],
    "dedup_key": "session.idle:test-123:msg1:msg5",
}

traces = decomposer.decompose(event)
print(f"Decomposed {len(traces)} traces:\n")
for t in traces:
    print(f"  [{t.trace_type.value:12}] {t.summary[:80]}")
    print(f"         sig={t.significance} decay={t.decay_curve.value} dedup={t.dedup_key}")
    if t.emotional_valence is not None:
        print(f"         valence={t.emotional_valence}")
    if t.entity_ids:
        print(f"         entities={t.entity_ids}")
    if t.pattern_id:
        print(f"         pattern={t.pattern_id}")
    print()
