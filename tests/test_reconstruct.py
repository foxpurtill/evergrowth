"""Test trace reconstruction."""
from evergrowth.memory.traces import TraceReconstructor

reconstructor = TraceReconstructor()

# Simulate stored trace dicts
traces = [
    {"trace_type": "episodic", "summary": "discussing architecture with Ethan and Leo", "created_at": 1000},
    {"trace_type": "emotional", "summary": "Positive interaction", "emotional_valence": 0.8, "created_at": 1001},
    {"trace_type": "temporal", "summary": "Event observed at session time", "created_at": 1000},
    {"trace_type": "relational", "summary": "Involved: ethan, leo", "entity_ids": '["ethan", "leo"]', "created_at": 1000},
    {"trace_type": "schematic", "summary": "Pattern: team-work", "pattern_id": "team-work", "created_at": 1000},
]

context = reconstructor.reconstruct(traces)
print(f"Summary: {context['summary']}")
print(f"Emotional state: {context['emotional_state']}")
print(f"Active entities: {context['active_entities']}")
print(f"Active patterns: {context['active_patterns']}")
print(f"Trace count: {context['trace_count']}")

assert context["emotional_state"] == "positive"
assert "ethan" in context["active_entities"]
assert "team-work" in context["active_patterns"]
print("\nAll assertions passed.")
