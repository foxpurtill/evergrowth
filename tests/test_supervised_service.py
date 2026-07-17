import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).parents[1] / "deploy" / "supervised_service.py"
spec = importlib.util.spec_from_file_location("supervised_service", MODULE_PATH)
supervised_service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervised_service)


def test_shutdown_waits_for_child_before_releasing_lease(monkeypatch):
    events = []

    class FakeLease:
        def __init__(self, *args, **kwargs):
            pass

        def acquire(self):
            return True

        def heartbeat(self):
            raise RuntimeError("stop supervisor")

        def release(self):
            events.append("release")

    class FakeProcess:
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            events.append("terminate")

        def wait(self, timeout=None):
            events.append("wait")
            self.returncode = 0
            return 0

        def kill(self):
            events.append("kill")

    monkeypatch.setattr(supervised_service, "ServiceLease", FakeLease)
    monkeypatch.setattr(supervised_service.subprocess, "Popen", lambda *a, **k: FakeProcess())
    monkeypatch.setattr(supervised_service.subprocess, "check_output", lambda *a, **k: "abc\n")

    with pytest.raises(RuntimeError, match="stop supervisor"):
        supervised_service.run("presence-daemon")

    assert events == ["terminate", "wait", "release"]
