import importlib.util
import sqlite3
from pathlib import Path

WRAPPER = Path.home() / "Ethan" / "hermes_delegate.py"
SPEC = importlib.util.spec_from_file_location("hermes_delegate_wrapper", WRAPPER)
wrapper = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(wrapper)


def test_recovery_stays_bound_to_first_created_session(tmp_path, monkeypatch):
    db_path = tmp_path / "state.db"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, role TEXT, content TEXT, timestamp REAL, finish_reason TEXT, active INTEGER)")
        db.execute("INSERT INTO messages VALUES (1, 'old', 'user', 'old', 1, NULL, 1)")
    monkeypatch.setattr(wrapper, "STATE_DB", db_path)
    boundary = wrapper.last_message_id()

    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO messages VALUES (2, 'session-a', 'user', 'same prompt', 2, NULL, 1)")
        db.execute("INSERT INTO messages VALUES (3, 'session-a', 'assistant', 'ANSWER_A', 3, 'stop', 1)")
        db.execute("INSERT INTO messages VALUES (4, 'session-b', 'user', 'same prompt', 4, NULL, 1)")

    chosen = wrapper.created_cli_session(boundary, "same prompt")
    assert chosen == "session-a"
    assert wrapper.final_answer(chosen) == "ANSWER_A"
