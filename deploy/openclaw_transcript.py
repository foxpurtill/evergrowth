"""Normalize OpenClaw JSONL transcripts into provider-neutral conversation events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def resolve_session_transcript(index_path: Path, session_key: str) -> Path | None:
    """Resolve the current transcript path for an OpenClaw session key."""
    try:
        sessions = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = sessions.get(session_key, {})
    raw_path = entry.get("sessionFile")
    if not raw_path:
        session_id = entry.get("sessionId")
        if not session_id:
            return None
        raw_path = str(index_path.parent / f"{session_id}.jsonl")
    path = Path(raw_path)
    return path if path.exists() else None


def _epoch_ms(value: str | None) -> int | None:
    if not value:
        return None
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def _visible_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = [item.get("text", "").strip() for item in content if item.get("type") == "text"]
    return "\n".join(part for part in parts if part)


def extract_conversation(path: Path, *, started_at: str, ended_at: str) -> list[dict]:
    """Return visible user/assistant messages inside an absence window."""
    start_ms = _epoch_ms(started_at)
    end_ms = _epoch_ms(ended_at)
    events: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if record.get("type") != "message":
            continue
        message = record.get("message", {})
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        timestamp = message.get("timestamp")
        if not isinstance(timestamp, int) or timestamp < start_ms or timestamp > end_ms:
            continue
        text = _visible_text(message.get("content"))
        if not text:
            continue
        if role == "user" and not message.get("senderId"):
            continue
        key = (role, text)
        if key in seen:
            continue
        seen.add(key)
        events.append({
            "role": role,
            "content": text,
            "occurred_at": datetime.fromtimestamp(timestamp / 1000, UTC).isoformat(),
            "channel": message.get("sourceChannel", "telegram"),
            "sender_id": message.get("senderId"),
        })
    return events


def build_briefing(events: list[dict]) -> str:
    """Render normalized events as a compact cross-channel return briefing."""
    if not events:
        return ""
    lines = []
    for event in events:
        speaker = "Patricia" if event.get("role") == "user" else "Ethan"
        lines.append(f"{speaker}: {event.get('content', '').strip()}")
    return "Telegram conversation during the absence:\n" + "\n".join(lines)
