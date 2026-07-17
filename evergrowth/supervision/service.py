"""Singleton service leases and bounded recovery supervision."""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class ServiceRecord:
    role: str
    pid: int
    owner_token: str
    started_at: float
    heartbeat_at: float
    version: str = ""
    command: str = ""


class ServiceLease:
    """Own one service role using an atomic, heartbeat-bearing lease file."""

    def __init__(self, role: str, state_dir: str | Path, *, version: str = "", command: str = ""):
        self.role = role
        self.state_dir = Path(state_dir).expanduser()
        self.path = self.state_dir / f"{role}.json"
        self.lock_path = self.state_dir / f"{role}.lock"
        self.version = version
        self.command = command
        self.owner_token = uuid.uuid4().hex
        self.record: ServiceRecord | None = None

    @contextmanager
    def _operation_lock(self, timeout_seconds: float = 5.0):
        self.state_dir.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + timeout_seconds
        while True:
            try:
                descriptor = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.write(descriptor, str(os.getpid()).encode("ascii"))
                os.close(descriptor)
                break
            except FileExistsError:
                try:
                    owner_pid = int(self.lock_path.read_text(encoding="ascii"))
                except (OSError, ValueError):
                    owner_pid = 0
                try:
                    lock_age = max(0.0, time.time() - self.lock_path.stat().st_mtime)
                except OSError:
                    lock_age = 0.0
                if (owner_pid > 0 and not self._pid_alive(owner_pid)) or (
                    owner_pid == 0 and lock_age > 5.0
                ):
                    try:
                        self.lock_path.unlink(missing_ok=True)
                    except PermissionError:
                        time.sleep(0.01)
                    continue
                if time.time() >= deadline:
                    raise TimeoutError(f"service lease operation busy: {self.role}")
                time.sleep(0.01)
        try:
            yield
        finally:
            for _ in range(50):
                try:
                    self.lock_path.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.01)

    def acquire(self) -> bool:
        with self._operation_lock():
            lease_exists = self.path.exists()
            existing = self.read()
            if lease_exists and existing is None:
                return False
            if existing and self._pid_alive(existing.pid):
                return False
            now = time.time()
            record = ServiceRecord(
                role=self.role,
                pid=os.getpid(),
                owner_token=self.owner_token,
                started_at=now,
                heartbeat_at=now,
                version=self.version,
                command=self.command,
            )
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(asdict(record), indent=2), encoding="utf-8")
            try:
                temporary.replace(self.path)
            except OSError:
                return False
            verified = self.read()
            if not verified or verified.owner_token != self.owner_token:
                return False
            self.record = record
            return True

    def heartbeat(self) -> None:
        if self.record is None:
            return
        with self._operation_lock():
            current = self.read()
            if not current or current.owner_token != self.owner_token:
                raise RuntimeError(f"service lease lost: {self.role}")
            self.record.heartbeat_at = time.time()
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(asdict(self.record), indent=2), encoding="utf-8"
            )
            temporary.replace(self.path)

    def release(self) -> None:
        with self._operation_lock():
            current = self.read()
            if current and current.owner_token == self.owner_token:
                self.path.unlink(missing_ok=True)
            self.record = None

    def read(self) -> ServiceRecord | None:
        try:
            return ServiceRecord(**json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, TypeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"service role already owned: {self.role}")
        return self

    def __exit__(self, *_):
        self.release()


@dataclass
class HealthReport:
    role: str
    state: str
    pid: int | None
    age_seconds: float | None
    version: str = ""
    reason: str = ""


class ServiceSupervisor:
    """Assess registered leases and recover only through explicit callbacks."""

    def __init__(self, state_dir: str | Path, stale_after_seconds: float = 90.0):
        self.state_dir = Path(state_dir).expanduser()
        self.stale_after_seconds = stale_after_seconds
        self.restart_handlers: dict[str, callable] = {}
        self.stop_handlers: dict[str, callable] = {}

    def register(self, role: str, *, restart=None, stop=None) -> None:
        if restart:
            self.restart_handlers[role] = restart
        if stop:
            self.stop_handlers[role] = stop

    def assess(self, role: str) -> HealthReport:
        lease = ServiceLease(role, self.state_dir)
        record = lease.read()
        if record is None:
            return HealthReport(role, "missing", None, None, reason="no lease")
        age = max(0.0, time.time() - record.heartbeat_at)
        if not lease._pid_alive(record.pid):
            return HealthReport(role, "dead", record.pid, age, record.version, "pid not alive")
        if age > self.stale_after_seconds:
            return HealthReport(role, "stale", record.pid, age, record.version, "heartbeat stale")
        return HealthReport(role, "healthy", record.pid, age, record.version)

    def recover(self, role: str) -> HealthReport:
        report = self.assess(role)
        if report.state == "healthy":
            return report
        restart = self.restart_handlers.get(role)
        if restart is None:
            report.reason += "; no registered restart handler"
            return report
        stop = self.stop_handlers.get(role)
        if stop and report.pid:
            stop(report.pid)
        restart()
        return self.assess(role)
