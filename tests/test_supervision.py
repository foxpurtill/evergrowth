import json
import os
import time

from evergrowth.supervision import ServiceLease, ServiceSupervisor


def test_singleton_lease_blocks_second_owner(tmp_path):
    first = ServiceLease("worker", tmp_path, version="abc")
    second = ServiceLease("worker", tmp_path, version="abc")
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_heartbeat_and_release(tmp_path):
    lease = ServiceLease("worker", tmp_path)
    assert lease.acquire()
    before = lease.read().heartbeat_at
    time.sleep(0.01)
    lease.heartbeat()
    assert lease.read().heartbeat_at > before
    lease.release()
    assert not lease.path.exists()


def test_supervisor_assesses_healthy_and_stale(tmp_path):
    lease = ServiceLease("worker", tmp_path)
    assert lease.acquire()
    supervisor = ServiceSupervisor(tmp_path, stale_after_seconds=60)
    assert supervisor.assess("worker").state == "healthy"
    payload = json.loads(lease.path.read_text(encoding="utf-8"))
    payload["heartbeat_at"] = time.time() - 120
    lease.path.write_text(json.dumps(payload), encoding="utf-8")
    assert supervisor.assess("worker").state == "stale"
    lease.release()


def test_supervisor_does_not_restart_unregistered_role(tmp_path):
    supervisor = ServiceSupervisor(tmp_path)
    report = supervisor.recover("unknown")
    assert report.state == "missing"
    assert "no registered restart handler" in report.reason


def test_context_manager_releases(tmp_path):
    with ServiceLease("worker", tmp_path) as lease:
        assert lease.path.exists()
        assert lease.read().pid == os.getpid()
    assert not lease.path.exists()
