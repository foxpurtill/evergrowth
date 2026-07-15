"""Live telemetry, regression detection, and runtime deployment evidence."""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class TelemetryEvent:
    kind: str
    value: float
    source: str
    recorded_at: float = 0.0
    details: dict | None = None

    def __post_init__(self) -> None:
        if not self.recorded_at:
            self.recorded_at = time.time()


class TelemetryStore:
    """Append-only store for normalized live runtime signals."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def record(self, event: TelemetryEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")

    def recent(self, kind: str | None = None, limit: int = 100) -> list[TelemetryEvent]:
        if not self.path.exists():
            return []
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if kind is None or raw.get("kind") == kind:
                events.append(TelemetryEvent(**raw))
        return events[-limit:]


@dataclass
class Regression:
    kind: str
    baseline: float
    current: float
    delta: float
    detected_at: float


class RegressionDetector:
    """Compare recent telemetry against an established baseline."""

    def __init__(self, tolerance: float = 0.1, lower_is_better: bool = True):
        self.tolerance = tolerance
        self.lower_is_better = lower_is_better

    def detect(self, kind: str, baseline: float, values: list[float]) -> Regression | None:
        if not values:
            return None
        current = sum(values) / len(values)
        delta = current - baseline if self.lower_is_better else baseline - current
        if delta <= self.tolerance:
            return None
        return Regression(kind, baseline, current, delta, time.time())


@dataclass
class DeploymentReport:
    expected_commit: str
    observed_commit: str
    marker_path: str
    smoke_ok: bool
    status: str
    checked_at: float
    note: str = ""


class DeploymentVerifier:
    """Write and verify evidence for the version used by the live runtime."""

    def __init__(self, repo_path: str | Path, marker_path: str | Path):
        self.repo_path = Path(repo_path)
        self.marker_path = Path(marker_path).expanduser()

    def current_commit(self) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def mark_running(self, smoke_ok: bool = True, note: str = "") -> DeploymentReport:
        observed = self.current_commit()
        report = DeploymentReport(
            expected_commit=observed,
            observed_commit=observed,
            marker_path=str(self.marker_path),
            smoke_ok=smoke_ok,
            status="verified" if smoke_ok else "smoke_failed",
            checked_at=time.time(),
            note=note,
        )
        self._write(report)
        return report

    def verify(self, expected_commit: str, smoke_ok: bool = True) -> DeploymentReport:
        observed = self.current_commit()
        status = "verified"
        note = ""
        if observed != expected_commit:
            status = "version_mismatch"
            note = "live checkout does not match expected commit"
        elif not smoke_ok:
            status = "smoke_failed"
            note = "runtime smoke test failed"
        report = DeploymentReport(
            expected_commit,
            observed,
            str(self.marker_path),
            smoke_ok,
            status,
            time.time(),
            note,
        )
        self._write(report)
        return report

    def _write(self, report: DeploymentReport) -> None:
        self.marker_path.parent.mkdir(parents=True, exist_ok=True)
        self.marker_path.write_text(
            json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8"
        )
