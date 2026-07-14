"""Regression tests for the deployed presence bridge daemon."""

import importlib.util
import json
from pathlib import Path

import pytest

DAEMON_PATH = Path(__file__).parents[1] / "deploy" / "evergrowth_presence_daemon.py"
SPEC = importlib.util.spec_from_file_location("evergrowth_presence_daemon", DAEMON_PATH)
daemon = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(daemon)


def test_parse_handoff_normalizes_spaces_and_hyphens(tmp_path, monkeypatch):
    handoff = tmp_path / "PRESENCE_HANDOFF.md"
    handoff.write_text(
        "Status: active\nLeft-at baseline: 2026-07-14T06:05:36.418Z\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(daemon, "HANDOFF", handoff)

    parsed = daemon.parse_handoff()

    assert parsed["left_at_baseline"] == "2026-07-14T06:05:36.418Z"


def test_build_away_event_uses_empty_reason_instead_of_null():
    event = daemon.build_event({
        "status": "active",
        "session_id": "session-1",
        "presence_id": "presence-1",
        "left_at_baseline": "2026-07-14T06:05:36.418Z",
    })

    assert event["occurred_at"] == "2026-07-14T06:05:36.418Z"
    assert event["reason"] == ""


def test_extract_mcp_payload_prefers_structured_content():
    payload = daemon.extract_mcp_payload({
        "structuredContent": {"status": "ok", "mode": "away"},
        "content": [{"text": "not json"}],
    })

    assert payload == {"status": "ok", "mode": "away"}


def test_extract_mcp_payload_skips_non_json_text_blocks():
    payload = daemon.extract_mcp_payload({
        "content": [
            {"text": "Tool completed successfully"},
            {"text": '{"status": "ok", "presence_id": "presence-1"}'},
        ]
    })

    assert payload["presence_id"] == "presence-1"


def test_extract_mcp_payload_rejects_missing_json():
    with pytest.raises(RuntimeError, match="no JSON payload"):
        daemon.extract_mcp_payload({"content": [{"text": "plain text only"}]})


def test_build_return_conversation_captures_visible_channel_messages(
    tmp_path, monkeypatch
):
    transcript = tmp_path / "telegram.jsonl"
    transcript.write_text(
        json.dumps({
            "type": "message",
            "message": {
                "role": "user",
                "content": "I'm back soon",
                "timestamp": 3000,
                "senderId": "patricia",
                "sourceChannel": "telegram",
            },
        })
        + "\n"
        + json.dumps({
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "I'll be here"}],
                "timestamp": 4000,
            },
        }),
        encoding="utf-8",
    )
    index = tmp_path / "sessions.json"
    index.write_text(
        json.dumps({daemon.TELEGRAM_SESSION_KEY: {"sessionFile": str(transcript)}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(daemon, "SESSIONS_INDEX", index)

    event = daemon.build_return_conversation(
        {
            "left_at_baseline": "1970-01-01T00:00:02Z",
            "returned_at": "1970-01-01T00:00:05Z",
        },
        {
            "event": "presence.return",
            "session_id": "session-1",
            "presence_id": "presence-1",
        },
    )

    assert event["event"] == "conversation.bridge"
    assert event["dedup_key"] == "conversation.bridge:presence-1"
    assert len(event["messages"]) == 2
    assert "Patricia: I'm back soon" in event["topics"][0]
