"""A bounded, auditable experiment loop inspired by autoresearch."""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import contextmanager
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path

MetricFn = Callable[[], float | Awaitable[float]]
ChangeFn = Callable[[], None | Awaitable[None]]


@dataclass
class ExperimentSpec:
    name: str
    hypothesis: str
    metric_name: str
    baseline: float
    lower_is_better: bool = True
    budget_seconds: float = 300.0
    minimum_improvement: float = 0.0
    attempt_id: str = ""


@dataclass
class ExperimentResult:
    name: str
    status: str
    baseline: float
    measured: float | None
    improvement: float
    duration_seconds: float
    note: str = ""


class ExperimentRunner:
    """Runs one reversible experiment and records the evidence."""

    def __init__(self, ledger_path: str | Path):
        self.ledger_path = Path(ledger_path).expanduser()

    async def run(
        self,
        spec: ExperimentSpec,
        apply_change: ChangeFn,
        evaluate: MetricFn,
        rollback: ChangeFn,
    ) -> ExperimentResult:
        started = time.monotonic()
        measured = None
        status = "discard"
        note = ""
        change_started = False
        try:
            change_started = True
            await self._call(apply_change)
            measured = float(await self._call(evaluate))
            duration = time.monotonic() - started
            if duration > spec.budget_seconds:
                note = "time budget exceeded"
            elif self._improved(spec, measured):
                status = "keep"
            else:
                note = "metric did not improve enough"
        except asyncio.CancelledError:
            if change_started:
                rollback_task = asyncio.create_task(self._call(rollback))
                try:
                    await asyncio.shield(rollback_task)
                except asyncio.CancelledError:
                    await rollback_task
            raise
        except Exception as exc:
            duration = time.monotonic() - started
            status = "crash"
            note = f"{type(exc).__name__}: {exc}"
        if status != "keep":
            await self._call(rollback)
        improvement = self._improvement(spec, measured)
        result = ExperimentResult(
            name=spec.name,
            status=status,
            baseline=spec.baseline,
            measured=measured,
            improvement=improvement,
            duration_seconds=duration,
            note=note,
        )
        self._append(spec, result)
        return result

    @staticmethod
    async def _call(fn):
        value = fn()
        if hasattr(value, "__await__"):
            return await value
        return value

    @staticmethod
    def _improvement(spec: ExperimentSpec, measured: float | None) -> float:
        if measured is None:
            return 0.0
        delta = spec.baseline - measured if spec.lower_is_better else measured - spec.baseline
        return delta

    def _improved(self, spec: ExperimentSpec, measured: float) -> bool:
        return self._improvement(spec, measured) > spec.minimum_improvement

    @contextmanager
    def _ledger_lock(self, timeout_seconds: float = 5.0):
        lock_path = self.ledger_path.with_suffix(self.ledger_path.suffix + ".lock")
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, str(os.getpid()).encode("ascii"))
                os.close(descriptor)
                break
            except FileExistsError:
                try:
                    owner_pid = int(lock_path.read_text(encoding="ascii"))
                except (OSError, ValueError):
                    owner_pid = 0
                owner_alive = False
                if owner_pid > 0:
                    try:
                        os.kill(owner_pid, 0)
                        owner_alive = True
                    except OSError:
                        pass
                try:
                    lock_age = max(0.0, time.time() - lock_path.stat().st_mtime)
                except OSError:
                    lock_age = 0.0
                if (owner_pid > 0 and not owner_alive) or (owner_pid == 0 and lock_age > 5.0):
                    try:
                        lock_path.unlink(missing_ok=True)
                    except PermissionError:
                        time.sleep(0.01)
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("experiment ledger is busy")
                time.sleep(0.01)
        try:
            yield
        finally:
            deadline = time.monotonic() + 1.0
            while True:
                try:
                    lock_path.unlink(missing_ok=True)
                    break
                except PermissionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.01)

    def _append(self, spec: ExperimentSpec, result: ExperimentResult) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self._ledger_lock():
            if spec.attempt_id and self.ledger_path.exists():
                for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
                    try:
                        existing = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if existing.get("spec", {}).get("attempt_id") == spec.attempt_id:
                        return
            entry = {"spec": asdict(spec), "result": asdict(result), "recorded_at": time.time()}
            needs_separator = False
            if self.ledger_path.exists() and self.ledger_path.stat().st_size:
                with self.ledger_path.open("rb") as existing:
                    existing.seek(-1, os.SEEK_END)
                    needs_separator = existing.read(1) != b"\n"
            with self.ledger_path.open("a", encoding="utf-8") as handle:
                if needs_separator:
                    handle.write("\n")
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
