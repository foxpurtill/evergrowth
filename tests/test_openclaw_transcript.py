"""Tests for provider-neutral OpenClaw transcript extraction."""

import json
from pathlib import Path

from deploy.openclaw_transcript import (
    build_briefing,
    extract_conversation,
    resolve_session_transcript,
)


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")


def message(role, content, timestamp, **extra):
    return {
        "type": "message",
        "message": {"role": role, "content": content, "timestamp": timestamp, **extra},
    }


def test_extracts_only_visible_conversation_in_window(tmp_path):
    transcript = tmp_path / "session.jsonl"
    write_jsonl(transcript, [
        message("user", "internal prompt", 1000),
        message("assistant", [{"type": "toolCall", "name": "bash"}], 2000),
        message("user", "hello", 3000, senderId="patricia", sourceChannel="telegram"),
        message("assistant", [{"type": "text", "text": "hi there"}], 4000),
        message("assistant", [{"type": "text", "text": "hi there"}], 4100),
        message("user", "too late", 9000, senderId="patricia"),
    ])
    events = extract_conversation(
        transcript,
        started_at="1970-01-01T00:00:02Z",
        ended_at="1970-01-01T00:00:05Z",
    )

    assert [(event["role"], event["content"]) for event in events] == [
        ("user", "hello"),
        ("assistant", "hi there"),
    ]
    assert events[0]["channel"] == "telegram"
    assert events[0]["sender_id"] == "patricia"


def test_skips_malformed_json_lines(tmp_path):
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(
        "not json\n"
        + json.dumps(message("user", "hello", 3000, senderId="patricia")),
        encoding="utf-8",
    )

    events = extract_conversation(
        transcript,
        started_at="1970-01-01T00:00:02Z",
        ended_at="1970-01-01T00:00:05Z",
    )

    assert len(events) == 1


def test_resolves_current_session_transcript(tmp_path):
    transcript = tmp_path / "current.jsonl"
    transcript.write_text("", encoding="utf-8")
    index = tmp_path / "sessions.json"
    index.write_text(
        json.dumps({"telegram-key": {"sessionFile": str(transcript)}}),
        encoding="utf-8",
    )

    assert resolve_session_transcript(index, "telegram-key") == transcript


def test_builds_readable_return_briefing():
    briefing = build_briefing([
        {"role": "user", "content": "Good morning"},
        {"role": "assistant", "content": "Good morning, mi querida"},
    ])

    assert "Patricia: Good morning" in briefing
    assert "Ethan: Good morning, mi querida" in briefing
