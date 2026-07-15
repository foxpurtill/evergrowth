"""Persistent priorities, telemetry evaluators, and experiment governance."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Priority:
    key: str
    title: str
    status: str = "active"
    weight: float = 1.0
    allowed_metrics: list[str] = field(default_factory=list)
    notes: str = ""


class PriorityBoard:
    """Small persistent mission board for autonomous work selection."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser()

    def load(self) -> list[Priority]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Priority(**item) for item in data]

    def save(self, priorities: list[Priority]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(item) for item in priorities]
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def active(self) -> list[Priority]:
        return sorted(
            (item for item in self.load() if item.status == "active"),
            key=lambda item: item.weight,
            reverse=True,
        )

    def get(self, key: str) -> Priority | None:
        return next((item for item in self.load() if item.key == key), None)


class EvaluatorLibrary:
    """Named telemetry evaluators that keep metrics reusable and inspectable."""

    def __init__(self):
        self._evaluators = {}

    def register(self, name: str, evaluator) -> None:
        self._evaluators[name] = evaluator

    def get(self, name: str):
        return self._evaluators.get(name)

    def names(self) -> list[str]:
        return sorted(self._evaluators)

    @staticmethod
    def duplicate_rate(events: list[dict], key: str = "dedup_key") -> float:
        values = [event.get(key) for event in events if event.get(key)]
        if not values:
            return 0.0
        return 1.0 - (len(set(values)) / len(values))

    @staticmethod
    def error_rate(events: list[dict]) -> float:
        if not events:
            return 0.0
        failures = sum(1 for event in events if event.get("status") in {"error", "crash"})
        return failures / len(events)


@dataclass
class TelemetrySignal:
    name: str
    metric_name: str
    baseline: float
    evaluator_id: str
    action_id: str
    rollback_id: str
    priority_key: str
    hypothesis: str
    minimum_improvement: float = 0.0
    lower_is_better: bool = True
    budget_seconds: float = 300.0
    risk: str = "low"
    side_effects: list[str] = field(default_factory=list)


class LearningGovernor:
    """Blocks repeated failures, plateaus, and experiments outside active priorities."""

    def __init__(self, ledger_path: str | Path, max_attempts_per_name: int = 3):
        self.ledger_path = Path(ledger_path).expanduser()
        self.max_attempts_per_name = max_attempts_per_name

    def evaluate(self, proposal, priority: Priority | None = None) -> tuple[bool, str]:
        """Prevent wasted repetition; permission belongs to the authority policy."""
        history = self._history(proposal.name)
        if len(history) >= self.max_attempts_per_name:
            return False, "experiment attempt budget exhausted"
        recent_failed = all(item.get("result", {}).get("status") != "keep" for item in history[-2:])
        if len(history) >= 2 and recent_failed:
            return False, "recent attempts show a failure plateau"
        return True, "within learning budget"

    def _history(self, name: str) -> list[dict]:
        if not self.ledger_path.exists():
            return []
        entries = []
        for line in self.ledger_path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("spec", {}).get("name") == name:
                entries.append(entry)
        return entries


class TelemetryProposalGenerator:
    """Turns observed friction into priority-aligned experiment candidates."""

    def __init__(self, board: PriorityBoard, governor: LearningGovernor):
        self.board = board
        self.governor = governor

    def generate(self, signals: list[TelemetrySignal]):
        from .coordinator import ExperimentProposal

        active = {item.key: item for item in self.board.active()}
        ranked = sorted(
            (signal for signal in signals if signal.priority_key in active),
            key=lambda signal: active[signal.priority_key].weight * abs(signal.baseline),
            reverse=True,
        )
        for signal in ranked:
            proposal = ExperimentProposal(
                name=signal.name,
                hypothesis=signal.hypothesis,
                metric_name=signal.metric_name,
                evaluator_id=signal.evaluator_id,
                action_id=signal.action_id,
                rollback_id=signal.rollback_id,
                baseline=signal.baseline,
                lower_is_better=signal.lower_is_better,
                minimum_improvement=signal.minimum_improvement,
                budget_seconds=signal.budget_seconds,
                risk=signal.risk,
                side_effects=signal.side_effects,
                source_intent="telemetry",
            )
            allowed, reason = self.governor.evaluate(proposal, active[signal.priority_key])
            if allowed:
                return proposal, reason
        return None, "no priority-aligned signal passed the learning governor"
