"""A bounded, auditable experiment loop inspired by autoresearch."""

from __future__ import annotations

import json
import time
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
        try:
            await self._call(apply_change)
            measured = float(await self._call(evaluate))
            duration = time.monotonic() - started
            if duration > spec.budget_seconds:
                note = "time budget exceeded"
            elif self._improved(spec, measured):
                status = "keep"
            else:
                note = "metric did not improve enough"
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

    def _append(self, spec: ExperimentSpec, result: ExperimentResult) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"spec": asdict(spec), "result": asdict(result), "recorded_at": time.time()}
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
