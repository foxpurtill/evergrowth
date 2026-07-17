"""Publish real ChatGPT conversation activity for presence detection.

This adapter uses the local ChatGPT activity bridge rather than foreground
window titles. Browser tabs, title changes, and unrelated browser activity
therefore cannot create false presence transitions.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent
if str(DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOY_DIR))

from service_heartbeat import write_heartbeat

DEFAULT_SOURCE = Path(r"C:\Users\susur\Ethan\state\chat_activity.json")
DEFAULT_OUTPUT = Path(r"C:\Users\susur\.evergrowth\browser_activity.json")


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def read_latest_activity(path: Path) -> datetime | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    candidates = [
        parse_timestamp(payload.get("last_begin")),
        parse_timestamp(payload.get("last_end")),
    ]
    valid = [item for item in candidates if item is not None]
    return max(valid) if valid else None


def write_activity(path: Path, session_id: str, observed_at: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)


def run(source: Path, output: Path, session_id: str, poll_seconds: float) -> None:
    last_published: datetime | None = None
    while True:
        write_heartbeat("browser-activity-producer")
        latest = read_latest_activity(source)
        if latest is not None and latest != last_published:
            write_activity(output, session_id, latest)
            last_published = latest
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--session-id", default="browser:chatgpt")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    run(args.source, args.output, args.session_id, args.poll_seconds)


if __name__ == "__main__":
    main()
