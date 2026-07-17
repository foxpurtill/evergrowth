"""Convert local browser activity timestamps into presence handoff transitions."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

DEPLOY_DIR = Path(__file__).resolve().parent
if str(DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOY_DIR))

from service_heartbeat import write_heartbeat

DEFAULT_ACTIVITY = Path(r"C:\Users\susur\.evergrowth\browser_activity.json")
DEFAULT_STATE = Path(r"C:\Users\susur\.evergrowth\activity_presence_state.json")
DEFAULT_HANDOFF = Path(r"C:\Users\susur\.openclaw\workspace\PRESENCE_HANDOFF.md")


@dataclass(frozen=True)
class ActivitySample:
    session_id: str
    observed_at: datetime


@dataclass
class DetectorState:
    mode: str = "present"
    session_id: str = "browser:chatgpt"
    presence_id: str | None = None
    away_at: str | None = None
    last_observed_at: str | None = None


def parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def read_activity(path: Path) -> ActivitySample | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        observed_at = parse_datetime(str(payload["observed_at"]))
        return ActivitySample(session_id=str(payload["session_id"]), observed_at=observed_at)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def load_state(path: Path) -> DetectorState:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return DetectorState(**payload)
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return DetectorState()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def save_state(path: Path, state: DetectorState) -> None:
    atomic_write(path, json.dumps(asdict(state), indent=2))


def write_handoff(
    path: Path,
    *,
    status: str,
    session_id: str,
    presence_id: str,
    away_at: str,
    returned_at: str | None = None,
) -> None:
    lines = [
        "# Presence handoff",
        "",
        f"Status: {status}",
        f"Session-id: {session_id}",
        f"Presence-id: {presence_id}",
        f"Left-at baseline: {away_at}",
    ]
    if returned_at:
        lines.append(f"Returned-at: {returned_at}")
    lines.extend(
        [
            "Reason: automatic-browser-inactivity",
            "Source: activity_presence_detector.py",
            "Outreach policy: relational-or-operational",
            "Relational outreach allowed: true",
            "Maximum relational messages per absence: 1",
            "",
            (
                "Instruction: On heartbeat, assess both operational significance and ordinary "
                "relational presence. A brief warm hello is allowed when timing feels natural. "
                "Avoid guilt, pressure, repetition, or manufactured urgency."
                if status == "active"
                else "Return instruction: create the cross-channel return briefing."
            ),
        ]
    )
    atomic_write(path, "\n".join(lines) + "\n")


def evaluate(
    state: DetectorState,
    sample: ActivitySample | None,
    now: datetime,
    away_after: timedelta,
    return_freshness: timedelta,
) -> str | None:
    if sample is not None:
        state.session_id = sample.session_id
        state.last_observed_at = utc_text(sample.observed_at)

    last_seen = None
    if state.last_observed_at:
        try:
            last_seen = parse_datetime(state.last_observed_at)
        except ValueError:
            state.last_observed_at = None

    if state.mode == "present":
        if last_seen is not None and now - last_seen >= away_after:
            state.mode = "away"
            state.presence_id = f"browser-presence:{uuid4().hex}"
            state.away_at = utc_text(last_seen)
            return "away"
        return None

    if (
        state.mode == "away"
        and sample is not None
        and now - sample.observed_at <= return_freshness
        and state.away_at is not None
        and state.presence_id is not None
    ):
        state.mode = "present"
        return "return"
    return None


def run_once(
    activity_path: Path,
    state_path: Path,
    handoff_path: Path,
    away_after: timedelta,
    return_freshness: timedelta,
    now: datetime | None = None,
) -> str | None:
    current = (now or datetime.now(UTC)).astimezone(UTC)
    state = load_state(state_path)
    transition = evaluate(
        state,
        read_activity(activity_path),
        current,
        away_after,
        return_freshness,
    )
    if transition == "away":
        write_handoff(
            handoff_path,
            status="active",
            session_id=state.session_id,
            presence_id=state.presence_id or "",
            away_at=state.away_at or utc_text(current),
        )
    elif transition == "return":
        write_handoff(
            handoff_path,
            status="returned",
            session_id=state.session_id,
            presence_id=state.presence_id or "",
            away_at=state.away_at or utc_text(current),
            returned_at=utc_text(current),
        )
        state.presence_id = None
        state.away_at = None
    save_state(state_path, state)
    return transition


def run(
    activity_path: Path,
    state_path: Path,
    handoff_path: Path,
    away_seconds: float,
    return_freshness_seconds: float,
    poll_seconds: float,
) -> None:
    away_after = timedelta(seconds=away_seconds)
    return_freshness = timedelta(seconds=return_freshness_seconds)
    while True:
        write_heartbeat("activity-presence-detector")
        run_once(activity_path, state_path, handoff_path, away_after, return_freshness)
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--activity", type=Path, default=DEFAULT_ACTIVITY)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--handoff", type=Path, default=DEFAULT_HANDOFF)
    parser.add_argument("--away-seconds", type=float, default=300.0)
    parser.add_argument("--return-freshness-seconds", type=float, default=20.0)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if args.once:
        run_once(
            args.activity,
            args.state,
            args.handoff,
            timedelta(seconds=args.away_seconds),
            timedelta(seconds=args.return_freshness_seconds),
        )
        return
    run(
        args.activity,
        args.state,
        args.handoff,
        args.away_seconds,
        args.return_freshness_seconds,
        args.poll_seconds,
    )


if __name__ == "__main__":
    main()
