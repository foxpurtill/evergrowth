"""A bounded, auditable experiment loop."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger("evergrowth.experiments.runner")

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
    apply_timeout: float = 30.0
    evaluate_timeout: float = 60.0
    rollback_timeout: float = 30.0
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
        self._active: set[str] = set()

    async def run(
        self,
        spec: ExperimentSpec,
        apply_change: ChangeFn,
        evaluate: MetricFn,
        rollback: ChangeFn,
    ) -> ExperimentResult:
        if spec.name in self._active:
            return ExperimentResult(
                name=spec.name,
                status="skipped",
                baseline=spec.baseline,
                measured=None,
                improvement=0.0,
                duration_seconds=0.0,
                note="already running",
            )
        self._active.add(spec.name)
        started = time.monotonic()
        measured = None
        status = "discard"
        note = ""
        try:
            await self._call_with_timeout(apply_change, spec.apply_timeout, "apply")
            measured = float(
                await self._call_with_timeout(evaluate, spec.evaluate_timeout, "evaluate")
            )
            elapsed = time.monotonic() - started
            if elapsed > spec.budget_seconds:
                note = f"time budget exceeded ({elapsed:.1f}s > {spec.budget_seconds}s)"
            elif self._improved(spec, measured):
                status = "keep"
            else:
                note = f"metric did not improve enough ({measured} vs baseline {spec.baseline})"
        except TimeoutError as exc:
            elapsed = time.monotonic() - started
            status = "crash"
            note = str(exc)
        except asyncio.CancelledError:
            elapsed = time.monotonic() - started
            status = "cancelled"
            note = "task cancelled during experiment"
            import asyncio as _asyncio
            try:
                await _asyncio.shield(
                    self._call_with_timeout(rollback, spec.rollback_timeout, "rollback")
                )
            except Exception as rb_exc:
                note += f"; rollback after cancel also failed: {rb_exc}"
            raise
        except Exception as exc:
            elapsed = time.monotonic() - started
            status = "crash"
            note = f"{type(exc).__name__}: {exc}"
        if status != "keep":
            await self._call_with_timeout(rollback, spec.rollback_timeout, "rollback")
        improvement = self._improvement(spec, measured)
        result = ExperimentResult(
            name=spec.name,
            status=status,
            baseline=spec.baseline,
            measured=measured,
            improvement=improvement,
            duration_seconds=time.monotonic() - started,
            note=note,
        )
        self._append(spec, result)
        self._active.discard(spec.name)
        logger.info(f"Experiment {spec.name}: {status} (improvement={improvement})")
        return result

    @staticmethod
    async def _call_with_timeout(fn, timeout: float, phase: str):
        value = fn()
        if hasattr(value, "__await__"):
            import asyncio
            try:
                value = await asyncio.wait_for(value, timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(f"{phase} phase timed out after {timeout}s")
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
        payload = json.dumps(entry, ensure_ascii=False)

        # Dedup by attempt_id if provided
        if spec.attempt_id:
            existing = self._read_ledger()
            if any(e.get("spec", {}).get("attempt_id") == spec.attempt_id for e in existing):
                logger.info(f"Experiment {spec.name}: attempt_id {spec.attempt_id} already recorded")
                return

        # Handle trailing partial JSON line from interrupted append
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        existing = b""
        if self.ledger_path.exists():
            existing = self.ledger_path.read_bytes()
            if existing and not existing.endswith(b"\n"):
                logger.warning("Ledger had trailing partial line — separating")
                existing = existing.rstrip(b"\r\n") + b"\n"

        # Atomic write via temp + replace
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            dir=self.ledger_path.parent, mode="wb", delete=False, prefix=".ledger_tmp_"
        )
        try:
            if existing:
                tmp.write(existing)
            tmp.write(payload.encode("utf-8"))
            tmp.write(b"\n")
            tmp.flush()
            os.replace(tmp.name, str(self.ledger_path))
        except Exception:
            try:
                Path(tmp.name).unlink()
            except Exception:
                pass
            raise

    def _read_ledger(self, path: Path | None = None) -> list[dict]:
        """Read all entries from the ledger for dedup."""
        ledger = path or self.ledger_path
        if not ledger.exists():
            return []
        entries = []
        for line in ledger.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    entries.append(parsed)
            except json.JSONDecodeError:
                continue
        return entries
