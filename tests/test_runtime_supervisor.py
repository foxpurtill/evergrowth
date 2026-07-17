import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "deploy" / "runtime_supervisor.py"
SPEC = importlib.util.spec_from_file_location("runtime_supervisor", MODULE_PATH)
supervisor = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = supervisor
SPEC.loader.exec_module(supervisor)


def test_assess_reports_current_and_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(supervisor, "HEARTBEAT_DIR", tmp_path)
    path = tmp_path / "presence-daemon.json"
    path.write_text(json.dumps({"heartbeat_at": 900}), encoding="utf-8")

    healthy = supervisor.assess("presence-daemon", now=1000)
    stale = supervisor.assess("presence-daemon", now=1101)

    assert healthy.state == "healthy"
    assert stale.state == "stale"


def test_restart_budget_and_cooldown():
    state = {"restart_attempts": {"worker": [800, 950]}}
    allowed, reason = supervisor.restart_allowed(state, "worker", 1000)
    assert not allowed
    assert "cooldown" in reason

    state = {"restart_attempts": {"worker": [100, 400, 700]}}
    allowed, reason = supervisor.restart_allowed(state, "worker", 1000)
    assert not allowed
    assert "budget" in reason


def test_soak_ledger_counts_health_and_resets_on_break(tmp_path, monkeypatch):
    heartbeat_dir = tmp_path / "heartbeats"
    heartbeat_dir.mkdir()
    state_path = tmp_path / "supervisor.json"
    monkeypatch.setattr(supervisor, "HEARTBEAT_DIR", heartbeat_dir)
    monkeypatch.setattr(supervisor, "STATE_PATH", state_path)
    monkeypatch.setattr(supervisor, "TASKS", {"worker": "Worker Task"})
    monkeypatch.setattr(supervisor, "start_task", lambda name: None)
    monkeypatch.setattr(
        supervisor,
        "assess_persistent",
        lambda now=None: supervisor.ServiceHealth(
            supervisor.PERSISTENT_ROLE, "healthy", 1.0, "test runtime healthy"
        ),
    )

    heartbeat = heartbeat_dir / "worker.json"
    discord_heartbeat = heartbeat_dir / f"{supervisor.DISCORD_ROLE}.json"
    heartbeat.write_text(json.dumps({"heartbeat_at": 990}), encoding="utf-8")
    discord_heartbeat.write_text(json.dumps({"heartbeat_at": 990}), encoding="utf-8")
    first = supervisor.run_once(now=1000)
    heartbeat.write_text(json.dumps({"heartbeat_at": 1050}), encoding="utf-8")
    discord_heartbeat.write_text(json.dumps({"heartbeat_at": 1050}), encoding="utf-8")
    second = supervisor.run_once(now=1060)

    assert first["soak"]["healthy_checks"] == 1
    assert second["soak"]["healthy_checks"] == 2
    assert second["soak"]["healthy_since"] == 1000

    heartbeat.write_text(json.dumps({"heartbeat_at": 1000}), encoding="utf-8")
    broken = supervisor.run_once(now=1201)
    assert broken["soak"]["healthy_checks"] == 0
    assert broken["soak"]["healthy_since"] is None
    assert broken["soak"]["last_break_at"] == 1201


def test_persistent_marker_reports_healthy_owner(tmp_path, monkeypatch):
    marker = tmp_path / "persistent-runtime.lock.json"
    marker.write_text(
        json.dumps({"pid": 321, "acquired_at": 900}), encoding="utf-8"
    )
    monkeypatch.setattr(supervisor, "PERSISTENT_MARKER", marker)
    monkeypatch.setattr(supervisor, "process_alive", lambda pid: pid == 321)

    health = supervisor.assess_persistent(now=1000)

    assert health.state == "healthy"
    assert health.age_seconds == 100


def test_missing_persistent_runtime_is_started_with_budget(tmp_path, monkeypatch):
    state_path = tmp_path / "supervisor.json"
    monkeypatch.setattr(supervisor, "STATE_PATH", state_path)
    monkeypatch.setattr(supervisor, "TASKS", {})
    monkeypatch.setattr(
        supervisor,
        "assess",
        lambda role, now=None: supervisor.ServiceHealth(
            role, "healthy", 1.0, "test service healthy"
        ),
    )
    monkeypatch.setattr(
        supervisor,
        "assess_discord",
        lambda now=None: supervisor.ServiceHealth(
            supervisor.DISCORD_ROLE, "healthy", 1.0, "test service healthy"
        ),
    )
    monkeypatch.setattr(
        supervisor,
        "assess_persistent",
        lambda now=None: supervisor.ServiceHealth(
            supervisor.PERSISTENT_ROLE, "missing", None, "no marker"
        ),
    )
    starts = []
    monkeypatch.setattr(
        supervisor, "start_persistent_runtime", lambda: starts.append(777) or 777
    )

    report = supervisor.run_once(now=1000)

    assert starts == [777]
    assert report["actions"][0]["action"] == "start_requested"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["restart_attempts"][supervisor.PERSISTENT_ROLE] == [1000]


def test_persistent_restart_respects_cooldown(tmp_path, monkeypatch):
    state_path = tmp_path / "supervisor.json"
    state_path.write_text(json.dumps({
        "restart_attempts": {supervisor.PERSISTENT_ROLE: [950]},
        "events": [],
    }), encoding="utf-8")
    monkeypatch.setattr(supervisor, "STATE_PATH", state_path)
    monkeypatch.setattr(supervisor, "TASKS", {})
    monkeypatch.setattr(
        supervisor,
        "assess",
        lambda role, now=None: supervisor.ServiceHealth(
            role, "healthy", 1.0, "test service healthy"
        ),
    )
    monkeypatch.setattr(
        supervisor,
        "assess_discord",
        lambda now=None: supervisor.ServiceHealth(
            supervisor.DISCORD_ROLE, "healthy", 1.0, "test service healthy"
        ),
    )
    monkeypatch.setattr(
        supervisor,
        "assess_persistent",
        lambda now=None: supervisor.ServiceHealth(
            supervisor.PERSISTENT_ROLE, "missing", None, "no marker"
        ),
    )
    monkeypatch.setattr(
        supervisor,
        "start_persistent_runtime",
        lambda: (_ for _ in ()).throw(AssertionError("must not launch")),
    )

    report = supervisor.run_once(now=1000)

    assert report["actions"][0]["action"] == "suppressed"
    assert "cooldown" in report["actions"][0]["reason"]


def test_missing_discord_bot_is_started_with_budget(tmp_path, monkeypatch):
    state_path = tmp_path / "supervisor.json"
    monkeypatch.setattr(supervisor, "STATE_PATH", state_path)
    monkeypatch.setattr(supervisor, "TASKS", {})
    monkeypatch.setattr(
        supervisor,
        "assess_persistent",
        lambda now=None: supervisor.ServiceHealth(
            supervisor.PERSISTENT_ROLE, "healthy", 1.0, "runtime healthy"
        ),
    )
    monkeypatch.setattr(
        supervisor,
        "assess_discord",
        lambda now=None: supervisor.ServiceHealth(
            supervisor.DISCORD_ROLE, "missing", None, "no heartbeat"
        ),
    )
    starts = []
    monkeypatch.setattr(
        supervisor, "start_discord_bot", lambda: starts.append(888) or 888
    )

    report = supervisor.run_once(now=1000)

    assert starts == [888]
    assert report["actions"][0]["role"] == supervisor.DISCORD_ROLE
    assert report["actions"][0]["action"] == "start_requested"
