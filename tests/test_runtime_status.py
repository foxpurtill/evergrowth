import importlib.util
import json
from pathlib import Path

STATUS_PATH = Path(__file__).parents[1] / "deploy" / "runtime_status.py"
SPEC = importlib.util.spec_from_file_location("runtime_status", STATUS_PATH)
status = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(status)


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def make_sources(tmp_path):
    sources = {name: tmp_path / f"{name}.json" for name in (
        "chat_activity", "browser_activity", "presence", "bridge", "selfprompt"
    )}
    sources["heartbeat_signal"] = tmp_path / "heartbeat_signal.txt"
    sources["supervisor"] = tmp_path / "runtime_supervisor_state.json"
    return sources


def test_snapshot_explains_noop_and_matching_activity(tmp_path):
    sources = make_sources(tmp_path)
    write_json(sources["chat_activity"], {"last_end": "2026-07-16T10:00:00Z"})
    write_json(sources["browser_activity"], {"observed_at": "2026-07-16T10:00:00Z"})
    write_json(sources["presence"], {"mode": "away", "presence_id": "p1"})
    write_json(sources["bridge"], {"last_decision": {"intents": [{
        "action": "noop", "is_noop": True, "noop_reason": "threshold not reached"
    }]}})
    write_json(sources["selfprompt"], {})
    sources["heartbeat_signal"].write_text("next:1440", encoding="utf-8")

    snapshot = status.build_snapshot(
        now=status.parse_time("2026-07-16T10:01:00Z"), sources=sources,
        service_dir=tmp_path / "services",
    )

    assert snapshot["overall"] == "healthy"
    assert snapshot["outreach"]["summary"] == "no-op: threshold not reached"
    assert snapshot["autonomy"]["heartbeat_signal"] == "next:1440"


def test_snapshot_flags_mismatched_activity_and_stale_service(tmp_path, monkeypatch):
    sources = make_sources(tmp_path)
    write_json(sources["chat_activity"], {"last_end": "2026-07-16T10:00:00Z"})
    write_json(sources["browser_activity"], {"observed_at": "2026-07-16T09:00:00Z"})
    write_json(sources["presence"], {"mode": "present"})
    write_json(sources["bridge"], {})
    write_json(sources["selfprompt"], {})
    sources["heartbeat_signal"].write_text("next:30", encoding="utf-8")
    service_dir = tmp_path / "services"
    service_dir.mkdir()
    write_json(service_dir / "presence-daemon.json", {
        "role": "presence-daemon", "pid": 123, "heartbeat_at":
        status.parse_time("2026-07-16T09:55:00Z")
    })
    monkeypatch.setattr(status, "process_alive", lambda pid: True)

    snapshot = status.build_snapshot(
        now=status.parse_time("2026-07-16T10:00:00Z"), sources=sources,
        service_dir=service_dir,
    )

    assert snapshot["overall"] == "attention"
    assert any("does not match" in issue for issue in snapshot["issues"])
    assert snapshot["services"][0]["state"] == "stale"
    rendered = status.render_markdown(snapshot)
    assert "## Needs attention" in rendered
    assert "presence-daemon: stale" in rendered


def test_main_runs_recovery_supervisor_before_writing_status(tmp_path, monkeypatch):
    calls = []
    output = tmp_path / "runtime-status.md"
    monkeypatch.setattr(status, "supervise_once", lambda: calls.append("supervised"))
    monkeypatch.setattr(
        "sys.argv", ["runtime_status.py", "--output", str(output)]
    )

    status.main()

    assert calls == ["supervised"]
    assert output.exists()
