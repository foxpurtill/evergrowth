"""Bridge autonomous intents into bounded, auditable experiments."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .runner import ExperimentResult, ExperimentRunner, ExperimentSpec


@dataclass
class ExperimentProposal:
    name: str
    hypothesis: str
    metric_name: str
    evaluator_id: str
    action_id: str
    rollback_id: str
    baseline: float
    lower_is_better: bool = True
    minimum_improvement: float = 0.0
    budget_seconds: float = 300.0
    risk: str = "low"
    side_effects: list[str] = field(default_factory=list)
    source_intent: str = ""


@dataclass
class GateDecision:
    approved: bool
    reason: str


class ExperimentAuthorityGate:
    """Approve only low-risk, measurable, reversible registered experiments."""

    def __init__(self, allowed_side_effects: set[str] | None = None):
        self.allowed_side_effects = allowed_side_effects or {"local_files", "memory"}

    def evaluate(self, proposal: ExperimentProposal, registry: ExperimentRegistry) -> GateDecision:
        if proposal.risk != "low":
            return GateDecision(False, "only low-risk experiments may run autonomously")
        missing = registry.missing(proposal)
        if missing:
            return GateDecision(False, f"unregistered adapters: {', '.join(missing)}")
        disallowed = sorted(set(proposal.side_effects) - self.allowed_side_effects)
        if disallowed:
            return GateDecision(False, f"disallowed side effects: {', '.join(disallowed)}")
        if proposal.budget_seconds <= 0:
            return GateDecision(False, "experiment budget must be positive")
        return GateDecision(True, "bounded, measurable, reversible, and registered")


class ExperimentRegistry:
    def __init__(self):
        self.evaluators: dict[str, Callable] = {}
        self.actions: dict[str, Callable] = {}
        self.rollbacks: dict[str, Callable] = {}

    def register_evaluator(self, name: str, fn: Callable) -> None:
        self.evaluators[name] = fn

    def register_action(self, name: str, fn: Callable) -> None:
        self.actions[name] = fn

    def register_rollback(self, name: str, fn: Callable) -> None:
        self.rollbacks[name] = fn

    def missing(self, proposal: ExperimentProposal) -> list[str]:
        missing = []
        if proposal.evaluator_id not in self.evaluators:
            missing.append(f"evaluator:{proposal.evaluator_id}")
        if proposal.action_id not in self.actions:
            missing.append(f"action:{proposal.action_id}")
        if proposal.rollback_id not in self.rollbacks:
            missing.append(f"rollback:{proposal.rollback_id}")
        return missing


class AutonomyCoordinator:
    """Turns approved research/skill intents into experiments and durable lessons."""

    def __init__(
        self,
        runner: ExperimentRunner,
        memory=None,
        registry: ExperimentRegistry | None = None,
        gate: ExperimentAuthorityGate | None = None,
        proposal_log_path: str | Path | None = None,
    ):
        self.runner = runner
        self.memory = memory
        self.registry = registry or ExperimentRegistry()
        self.gate = gate or ExperimentAuthorityGate()
        self.proposal_log_path = Path(
            proposal_log_path or runner.ledger_path.with_name("experiment_proposals.jsonl")
        ).expanduser()

    async def handle_intent(self, intent, context: dict) -> dict:
        if getattr(intent, "action", "") not in {"research", "develop_skill"}:
            return {"status": "ignored", "reason": "intent is not experimental"}
        proposal = self.propose(intent, context)
        if proposal is None:
            return {"status": "no_proposal", "reason": "no measurable candidate in context"}
        decision = self.gate.evaluate(proposal, self.registry)
        self._log_proposal(proposal, decision)
        if not decision.approved:
            return {"status": "rejected", "reason": decision.reason, "proposal": asdict(proposal)}

        spec = ExperimentSpec(
            name=proposal.name,
            hypothesis=proposal.hypothesis,
            metric_name=proposal.metric_name,
            baseline=proposal.baseline,
            lower_is_better=proposal.lower_is_better,
            budget_seconds=proposal.budget_seconds,
            minimum_improvement=proposal.minimum_improvement,
        )
        result = await self.runner.run(
            spec,
            self.registry.actions[proposal.action_id],
            self.registry.evaluators[proposal.evaluator_id],
            self.registry.rollbacks[proposal.rollback_id],
        )
        await self._remember(proposal, result)
        return {"status": "completed", "proposal": asdict(proposal), "result": asdict(result)}

    def propose(self, intent, context: dict) -> ExperimentProposal | None:
        candidate = context.get("experiment_candidate")
        if not isinstance(candidate, dict):
            return None
        required = {
            "name",
            "hypothesis",
            "metric_name",
            "evaluator_id",
            "action_id",
            "rollback_id",
            "baseline",
        }
        if not required.issubset(candidate):
            return None
        values = {key: candidate[key] for key in required}
        for key in (
            "lower_is_better",
            "minimum_improvement",
            "budget_seconds",
            "risk",
            "side_effects",
        ):
            if key in candidate:
                values[key] = candidate[key]
        values["source_intent"] = getattr(intent, "action", "")
        return ExperimentProposal(**values)

    async def _remember(self, proposal: ExperimentProposal, result: ExperimentResult) -> None:
        if self.memory is None or not hasattr(self.memory, "store"):
            return
        content = (
            f"Autonomous experiment {proposal.name}: {result.status}; "
            f"{proposal.metric_name} {result.baseline} -> {result.measured}; "
            f"improvement={result.improvement}; {result.note}"
        )
        await self.memory.store(
            content,
            category="experiment",
            importance=7,
            tags=["autonomy", proposal.source_intent, result.status],
        )

    def _log_proposal(self, proposal: ExperimentProposal, decision: GateDecision) -> None:
        self.proposal_log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "proposal": asdict(proposal),
            "gate": asdict(decision),
            "recorded_at": time.time(),
        }
        with self.proposal_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
