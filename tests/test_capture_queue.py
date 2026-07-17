import json

import pytest

from evergrowth.memory.capture_queue import CaptureQueueConsumer


class FlakyMemory:
    def __init__(self):
        self.calls = 0

    async def decompose_and_store(self, event):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary outage")
        return [event]


@pytest.mark.asyncio
async def test_transient_failure_remains_queued_for_retry(tmp_path):
    queue = tmp_path / "capture.jsonl"
    archive = tmp_path / "capture.done.jsonl"
    event = {"dedup_key": "event-1", "content": "remember me"}
    queue.write_text(json.dumps(event), encoding="utf-8")
    memory = FlakyMemory()
    consumer = CaptureQueueConsumer(memory, queue, archive)

    first = await consumer.process_all()
    assert first["errors"] == 1
    assert json.loads(queue.read_text(encoding="utf-8")) == event
    assert not archive.exists()

    second = await consumer.process_all()
    assert second["stored"] == 1
    assert memory.calls == 2
    assert queue.read_text(encoding="utf-8") == ""
    assert json.loads(archive.read_text(encoding="utf-8")) == event
