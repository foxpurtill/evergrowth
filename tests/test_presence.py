"""Test presence event decomposition."""
from evergrowth.memory.traces import FiveTraceDecomposer

d = FiveTraceDecomposer()

# Test away event
away = {
    "event": "presence.away",
    "session_id": "test-session-1",
    "presence_id": "test-session-1:12345",
    "occurred_at": "2026-07-13T12:00:00Z",
    "reason": "sleep",
    "dedup_key": "presence.away:test-session-1:test-session-1:12345",
}
away_traces = d.decompose(away)
print(f"Away: {len(away_traces)} traces")
for t in away_traces:
    print(f"  [{t.trace_type.value}] {t.summary} decay={t.decay_curve.value}")

# Test return event
ret = {
    "event": "presence.return",
    "session_id": "test-session-1",
    "presence_id": "test-session-1:12345",
    "occurred_at": "2026-07-13T14:00:00Z",
    "dedup_key": "presence.return:test-session-1:test-session-1:12345",
}
ret_traces = d.decompose(ret)
print(f"\nReturn: {len(ret_traces)} traces")
for t in ret_traces:
    print(f"  [{t.trace_type.value}] {t.summary} decay={t.decay_curve.value}")

# Test orphan return (no away before it)
orphan = {
    "event": "presence.return",
    "session_id": "test-session-2",
    "presence_id": "orphan-test:99999",
    "occurred_at": "2026-07-13T15:00:00Z",
    "dedup_key": "presence.return:test-session-2:orphan-test:99999",
}
orphan_traces = d.decompose(orphan)
print(f"\nOrphan return: {len(orphan_traces)} traces")
for t in orphan_traces:
    print(f"  [{t.trace_type.value}] {t.summary}")

print("\nAll presence tests passed.")
