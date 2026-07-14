"""Tests for automatic browser absence and return detection."""

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

DETECTOR_PATH = Path(__file__).parents[1] / "deploy" / "activity_presence_detector.py"
SPEC = importlib.util.spec_from_file_location("activity_presence_detector", DETECTOR_PATH)
detector = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = detector
SPEC.loader.exec_module(detector)


def write_activity(path: Path, observed_at: str, session_id: str = "browser:chatgpt"):
    path.write_text(
        json.dumps({"session_id": session_id, "observed_at": observed_at}),
        encoding="utf-8",
    )


def test_read_activity_rejects_invalid_payload(tmp_path):
    path = tmp_path / "activity.json"
    path.write_text("not json", encoding="utf-8")

    assert detector.read_activity(path) is None


def test_stale_activity_emits_away_once(tmp_path):
    activity = tmp_path / "activity.json"
    state = tmp_path / "state.json"
    handoff = tmp_path / "handoff.md"
    write_activity(activity, "2026-07-14T09:00:00Z")
    now = datetime(2026, 7, 14, 9, 6, tzinfo=UTC)

    first = detector.run_once(
        activity, state, handoff, timedelta(minutes=5), timedelta(seconds=20), now
    )
    second = detector.run_once(
        activity, state, handoff, timedelta(minutes=5), timedelta(seconds=20), now
    )

    assert first == "away"
    assert second is None
    text = handoff.read_text(encoding="utf-8")
    assert "Status: active" in text
    assert "Reason: automatic-browser-inactivity" in text


def test_fresh_activity_pairs_return_with_same_presence_id(tmp_path):
    activity = tmp_path / "activity.json"
    state = tmp_path / "state.json"
    handoff = tmp_path / "handoff.md"
    write_activity(activity, "2026-07-14T09:00:00Z")
    away_now = datetime(2026, 7, 14, 9, 6, tzinfo=UTC)
    detector.run_once(
        activity, state, handoff, timedelta(minutes=5), timedelta(seconds=20), away_now
    )
    away_text = handoff.read_text(encoding="utf-8")
    presence_line = next(line for line in away_text.splitlines() if line.startswith("Presence-id:"))
    presence_id = presence_line.split(": ", 1)[1]

    write_activity(activity, "2026-07-14T09:06:10Z")
    transition = detector.run_once(
        activity,
        state,
        handoff,
        timedelta(minutes=5),
        timedelta(seconds=20),
        datetime(2026, 7, 14, 9, 6, 11, tzinfo=UTC),
    )

    text = handoff.read_text(encoding="utf-8")
    assert transition == "return"
    assert "Status: returned" in text
    assert f"Presence-id: {presence_id}" in text
    persisted = json.loads(state.read_text(encoding="utf-8"))
    assert persisted["mode"] == "present"
    assert persisted["presence_id"] is None


def test_restart_preserves_away_state(tmp_path):
    state = tmp_path / "state.json"
    original = detector.DetectorState(
        mode="away",
        session_id="browser:chatgpt",
        presence_id="presence-1",
        away_at="2026-07-14T09:00:00Z",
        last_observed_at="2026-07-14T09:00:00Z",
    )
    detector.save_state(state, original)

    loaded = detector.load_state(state)

    assert loaded == original
