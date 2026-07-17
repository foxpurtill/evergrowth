import asyncio
from contextlib import suppress

import pytest

from evergrowth.heartbeat.engine import HeartbeatEngine


@pytest.mark.asyncio
async def test_stop_cancels_inflight_fire_before_restart_consumes_signal(tmp_path):
    engine = HeartbeatEngine.__new__(HeartbeatEngine)
    engine._active = 1
    engine._timer = None
    engine._fire_task = None
    engine._beat_count = 0
    engine._first_beat = True
    engine._user_interval = 5
    engine._last_interval = 5
    engine.capture_consumer = None
    engine.data_dir = tmp_path
    engine.signal_path = tmp_path / "heartbeat_signal.txt"
    engine._log = lambda message: None

    wait_started = asyncio.Event()
    release_wait = asyncio.Event()
    signal_consumed = False
    schedule_calls = []

    async def build_prompt():
        return "test heartbeat"

    async def wait_for_signal():
        nonlocal signal_consumed
        wait_started.set()
        await release_wait.wait()
        signal_consumed = True
        return True

    engine._build_prompt = build_prompt
    engine._wait_for_signal = wait_for_signal
    engine._schedule_next = lambda delay_minutes: schedule_calls.append(delay_minutes)

    task = asyncio.create_task(engine._fire())
    engine._fire_task = task
    await wait_started.wait()

    engine.stop()
    engine._active = 1  # Simulate an immediate restart.
    release_wait.set()

    with suppress(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    assert task.cancelled()
    assert signal_consumed is False
    assert schedule_calls == []


def test_presence_state_write_failure_preserves_previous_json(tmp_path, monkeypatch):
    class Mode:
        value = "away"

    class SelfPrompt:
        mode = Mode()

    engine = HeartbeatEngine.__new__(HeartbeatEngine)
    engine.self_prompt = SelfPrompt()
    engine._presence_context = {"presence_id": "new"}
    engine._away_started_at = 123.0
    engine.presence_state_path = tmp_path / "presence_runtime.json"
    previous = '{"mode": "return", "context": {"presence_id": "old"}}'
    engine.presence_state_path.write_text(previous, encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("simulated interruption")

    monkeypatch.setattr("evergrowth.heartbeat.engine.os.replace", fail_replace)

    with pytest.raises(OSError, match="simulated interruption"):
        engine._save_presence_state()

    assert engine.presence_state_path.read_text(encoding="utf-8") == previous


def test_default_interval_is_starting_cadence_not_forced_override(tmp_path):
    from types import SimpleNamespace

    class Config:
        heartbeat = SimpleNamespace(default_interval_minutes=30, character="§")

        @staticmethod
        def resolve_data_dir():
            return tmp_path

    engine = HeartbeatEngine(Config(), memory=None, identity=None)

    assert engine._user_interval is None
    assert engine._last_interval == 30


@pytest.mark.asyncio
async def test_fire_clears_stale_signal_before_publishing_prompt(tmp_path):
    engine = HeartbeatEngine.__new__(HeartbeatEngine)
    engine._active = 1
    engine._beat_count = 0
    engine._first_beat = True
    engine._user_interval = None
    engine._last_interval = 30
    engine.capture_consumer = None
    engine.data_dir = tmp_path
    engine.signal_path = tmp_path / "heartbeat_signal.txt"
    engine.signal_path.write_text("next:999", encoding="utf-8")
    engine._log = lambda message: None
    engine._schedule_next = lambda delay_minutes: None

    async def build_prompt():
        return "fresh prompt"

    async def wait_for_signal():
        assert not engine.signal_path.exists()
        return False

    engine._build_prompt = build_prompt
    engine._wait_for_signal = wait_for_signal

    await engine._fire()
    assert (tmp_path / "heartbeat_prompt.txt").read_text() == "fresh prompt"


@pytest.mark.asyncio
async def test_fire_does_not_queue_behind_processing_prompt(tmp_path):
    engine = HeartbeatEngine.__new__(HeartbeatEngine)
    engine._active = 1
    engine._beat_count = 0
    engine._first_beat = True
    engine._user_interval = None
    engine._last_interval = 30
    engine.capture_consumer = None
    engine.data_dir = tmp_path
    engine.signal_path = tmp_path / "heartbeat_signal.txt"
    processing = tmp_path / "heartbeat_prompt.processing"
    processing.write_text("recover me", encoding="utf-8")
    engine._log = lambda message: None
    engine._schedule_next = lambda delay_minutes: None

    async def wait_for_signal():
        assert processing.read_text() == "recover me"
        assert not (tmp_path / "heartbeat_prompt.txt").exists()
        return False

    async def build_prompt():
        return "must not be queued"

    engine._build_prompt = build_prompt
    engine._wait_for_signal = wait_for_signal
    await engine._fire()
