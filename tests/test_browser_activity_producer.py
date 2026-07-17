import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

PRODUCER_PATH = Path(__file__).parents[1] / "deploy" / "browser_activity_producer.py"
SPEC = importlib.util.spec_from_file_location("browser_activity_producer", PRODUCER_PATH)
producer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(producer)


def test_reads_latest_real_chat_activity(tmp_path):
    source = tmp_path / "chat_activity.json"
    source.write_text(json.dumps({
        "last_begin": "2026-07-16T08:10:00+00:00",
        "last_end": "2026-07-16T08:11:30+00:00",
    }), encoding="utf-8")
    assert producer.read_latest_activity(source) == datetime(
        2026, 7, 16, 8, 11, 30, tzinfo=UTC
    )


def test_missing_or_invalid_activity_returns_none(tmp_path):
    missing = tmp_path / "missing.json"
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    assert producer.read_latest_activity(missing) is None
    assert producer.read_latest_activity(invalid) is None
