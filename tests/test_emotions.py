"""Test emotional valence detection."""
from evergrowth.memory.traces import FiveTraceDecomposer

d = FiveTraceDecomposer()

# Test 1: Positive event
event1 = {
    "topic": "love how this turned out",
    "topics": ["love how this turned out", "happy with the results"],
    "keywords": ["writing", "thanks"],
}
traces = d.decompose(event1)
print("=== Positive event ===")
for t in traces:
    if t.trace_type.value == "emotional":
        print(f"  Emotional: valence={t.emotional_valence} — {t.summary}")
    elif t.trace_type.value == "relational":
        print(f"  Relational: {t.summary}")
    elif t.trace_type.value == "schematic":
        print(f"  Schematic: {t.summary}")
    else:
        print(f"  [{t.trace_type.value}] {t.summary}")

# Test 2: Negative event
event2 = {
    "topic": "frustrated with server issues",
    "topics": ["frustrated with server issues", "difficult debugging session"],
    "keywords": ["fixing"],
}
traces2 = d.decompose(event2)
print("\n=== Negative event ===")
for t in traces2:
    if t.trace_type.value == "emotional":
        print(f"  Emotional: valence={t.emotional_valence} — {t.summary}")
    elif t.trace_type.value == "schematic":
        print(f"  Schematic: {t.summary}")
    else:
        print(f"  [{t.trace_type.value}] {t.summary}")

# Test 3: Fox mentioning Patricia
event3 = {
    "topic": "Patricia will help with testing",
    "topics": ["Patricia will help with testing"],
    "keywords": ["collaboration"],
}
traces3 = d.decompose(event3)
print("\n=== Patricia event ===")
for t in traces3:
    if t.trace_type.value == "relational":
        print(f"  Relational: {t.summary}")
        print(f"    entities={t.entity_ids}")
    else:
        print(f"  [{t.trace_type.value}] {t.summary}")
