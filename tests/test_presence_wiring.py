"""Regression tests for production presence-to-self-prompt wiring."""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from evergrowth.heartbeat.engine import HeartbeatEngine
from evergrowth.mcp.server import EvergrowthMCPServer
from evergrowth.selfprompt.engine import Intent, OutreachGate, PresenceMode


class RecordingSelfPrompt:
    def __init__(self):
        self.mode = PresenceMode.RETURN
        self.mode_changes = []
        self.contexts = []

    def set_mode(self, mode, presence_id=""):
        self.mode = mode
        self.mode_changes.append((mode, presence_id))

    async def select_intent(self, context):
        self.contexts.append(dict(context))
        return [Intent("noop", "test", 0.0, OutreachGate.RELATIONAL, is_noop=True)]


class MemoryStub:
    async def reconstruct_context(self, limit=20):
        return "No trace context available"

    async def generate_context_cache(self):
        return ""


class CaptureMemoryStub:
    async def decompose_and_store(self, event):
        return [{"trace_type": "episodic"}]


def heartbeat_config(tmp_path: Path):
    heartbeat = SimpleNamespace(
        default_interval_minutes=30,
        initial_delay_minutes=1,
        response_timeout_seconds=1,
        character="§",
    )
    return SimpleNamespace(heartbeat=heartbeat, resolve_data_dir=lambda: tmp_path)


@pytest.mark.asyncio
async def test_presence_events_switch_mode_and_track_utc_elapsed(tmp_path, monkeypatch):
    prompt = RecordingSelfPrompt()
    engine = HeartbeatEngine(
        heartbeat_config(tmp_path), MemoryStub(), None, self_prompt=prompt
    )
    started = time.time() - 1900
    occurred_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))

    result = engine.update_presence({
        "event": "presence.away",
        "presence_id": "presence-1",
        "occurred_at": occurred_at,
        "relational_outreach_allowed": True,
        "topics": ["continuity"],
    })

    assert result["mode"] == "away"
    assert prompt.mode_changes[-1] == (PresenceMode.AWAY, "presence-1")
    assert engine._away_started_at == pytest.approx(started, abs=1.0)

    monkeypatch.setattr(time, "time", lambda: started + 1900)
    await engine._build_prompt()
    assert prompt.contexts[-1]["elapsed_seconds"] == pytest.approx(1900, abs=1.0)


@pytest.mark.asyncio
async def test_heartbeat_evaluates_self_prompt_on_every_beat(tmp_path, monkeypatch):
    prompt = RecordingSelfPrompt()
    engine = HeartbeatEngine(
        heartbeat_config(tmp_path), MemoryStub(), None, self_prompt=prompt
    )
    engine.update_presence({
        "event": "presence.away",
        "presence_id": "presence-2",
        "occurred_at": "2026-07-13T18:00:00Z",
        "relational_outreach_allowed": True,
    })
    monkeypatch.setattr(time, "time", lambda: 1783969200.0)

    await engine._build_prompt()
    engine._first_beat = False
    await engine._build_prompt()

    assert len(prompt.contexts) == 2
    assert all(c["presence_id"] == "presence-2" for c in prompt.contexts)
    assert all(c["elapsed_seconds"] >= 0 for c in prompt.contexts)


@pytest.mark.asyncio
async def test_capture_submit_updates_presence_after_storage():
    heartbeat = SimpleNamespace(update_presence=lambda event: {
        "status": "updated", "mode": "away", "presence_id": event["presence_id"]
    })
    server = EvergrowthMCPServer(
        config=None,
        memory=CaptureMemoryStub(),
        skills=None,
        identity=None,
        heartbeat=heartbeat,
    )

    result = await server._capture_submit({
        "event": "presence.away",
        "session_id": "session-1",
        "presence_id": "presence-3",
    })

    assert result["status"] == "ok"
    assert result["traces_stored"] == 1
    assert result["presence_update"]["presence_id"] == "presence-3"


@pytest.mark.asyncio
async def test_presence_state_survives_engine_restart(tmp_path, monkeypatch):
    started = time.time() - 1900
    occurred_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started))
    first_prompt = RecordingSelfPrompt()
    first = HeartbeatEngine(
        heartbeat_config(tmp_path), MemoryStub(), None, self_prompt=first_prompt
    )
    first.update_presence({
        "event": "presence.away",
        "presence_id": "presence-persisted",
        "occurred_at": occurred_at,
        "relational_outreach_allowed": True,
    })

    second_prompt = RecordingSelfPrompt()
    second = HeartbeatEngine(
        heartbeat_config(tmp_path), MemoryStub(), None, self_prompt=second_prompt
    )
    monkeypatch.setattr(time, "time", lambda: started + 1900)
    decision = await second.evaluate_self_prompt()

    assert second_prompt.mode == PresenceMode.AWAY
    assert decision["presence_id"] == "presence-persisted"
    assert decision["elapsed_seconds"] == pytest.approx(1900, abs=1.0)
    assert second_prompt.contexts[-1]["relational_outreach_allowed"] is True


@pytest.mark.asyncio
async def test_mcp_heartbeat_evaluate_returns_engine_decision():
    class EvaluatingHeartbeat:
        async def evaluate_self_prompt(self):
            return {
                "status": "ok",
                "mode": "away",
                "presence_id": "presence-4",
                "intents": [{"action": "check_in", "is_noop": False}],
            }

    server = EvergrowthMCPServer(
        config=None,
        memory=None,
        skills=None,
        identity=None,
        heartbeat=EvaluatingHeartbeat(),
    )

    result = await server._heartbeat_evaluate({})

    assert result["status"] == "ok"
    assert result["mode"] == "away"
    assert result["intents"][0]["action"] == "check_in"
