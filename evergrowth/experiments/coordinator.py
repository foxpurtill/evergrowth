"""Bridge autonomous intents into bounded, auditable experiments."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

from .runner import ExperimentResult, ExperimentRunner, ExperimentSpec

logger = logging.getLogger("evergrowth.experiments.coordinator")


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
    external: bool = False
    reversible: bool = True
    costs_money: bool = False
    privacy_sensitive: bool = False
    affects_others: bool = False
    source_intent: str = ""


@dataclass
class ActionRequest:
    name: str
    action_id: str
    reason: str = ""
    risk: str = "low"
    side_effects: list[str] = field(default_factory=list)
    external: bool = False
    reversible: bool = True
    costs_money: bool = False
    privacy_sensitive: bool = False
    affects_others: bool = False
    source_intent: str = ""


class ActionLane(Enum):
    ACT = "act"
    ACT_AND_REPORT = "act_and_report"
    ASK = "ask"


@dataclass
class GateDecision:
    approved: bool
    reason: str
    lane: ActionLane = ActionLane.ACT


class ExperimentAuthorityGate:
    """One boundary policy: broad interior freedom, hard stops at consequence."""

    def classify(self, action) -> GateDecision:
        consequential = (
            action.costs_money
            or action.privacy_sensitive
            or not action.reversible
            or (action.external and action.affects_others)
            or action.risk not in {"low", "medium"}
        )
        if consequential:
            return GateDecision(False, "consequential boundary requires approval", ActionLane.ASK)
        live_side_effects = set(action.side_effects) - {"memory", "local_files", "sandbox"}
        if action.external or live_side_effects:
            return GateDecision(
                True, "reversible low-risk live action; act and report", ActionLane.ACT_AND_REPORT
            )
        return GateDecision(True, "internal and reversible; free to act", ActionLane.ACT)

    def evaluate(self, proposal: ExperimentProposal, registry: ExperimentRegistry) -> GateDecision:
        decision = self.classify(proposal)
        if not decision.approved:
            return decision
        missing = registry.missing(proposal)
        if missing:
            return GateDecision(
                False, f"cannot execute; missing adapters: {', '.join(missing)}", decision.lane
            )
        if proposal.budget_seconds <= 0:
            return GateDecision(False, "cannot execute; budget must be positive", decision.lane)
        return decision


class ExperimentRegistry:
    """Registry of evaluators, actions, and rollbacks available to experiments."""

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


def _parse_candidates_from_response(response: str) -> dict:
    """Scan a DI response for experiment/action candidates.

    Looks for fenced blocks labeled `experiment` or `action`:
      ```experiment
      { "name": "...", ... }
      ```
    """
    import re

    candidates: dict[str, dict | None] = {"experiment": None, "action": None}

    for kind in ("experiment", "action"):
        pattern = rf"```{kind}\s*\n(.*?)```"
        match = re.search(pattern, response, re.DOTALL)
        if match:
            try:
                candidates[kind] = json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse {kind} candidate from response")
                candidates[kind] = {"raw": match.group(1).strip()}

    return candidates


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
            proposal_log_path or runner.ledger_path.with_name("proposals.jsonl")
        ).expanduser()

    def candidates_from_response(self, response: str) -> dict:
        """Parse experiment/action candidates from a DI response."""
        return _parse_candidates_from_response(response)

    async def handle_candidates(self, candidates: dict, intent=None, context: dict | None = None):
        """Process parsed candidates and return results."""
        results = []

        if candidates.get("action"):
            req = ActionRequest(
                **{
                    "name": candidates["action"].get("name", "unnamed"),
                    "action_id": candidates["action"].get("action_id", ""),
                    "reason": candidates["action"].get("reason", ""),
                    "risk": candidates["action"].get("risk", "low"),
                    "side_effects": candidates["action"].get("side_effects", []),
                    "external": candidates["action"].get("external", False),
                    "reversible": candidates["action"].get("reversible", True),
                    "costs_money": candidates["action"].get("costs_money", False),
                    "privacy_sensitive": candidates["action"].get("privacy_sensitive", False),
                    "affects_others": candidates["action"].get("affects_others", False),
                    "source_intent": getattr(intent, "action", "") if intent else "heartbeat",
                }
            )
            result = await self._run_direct(req)
            results.append(result)

        if candidates.get("experiment"):
            proposal_dict = dict(candidates["experiment"])
            required = {
                "name", "hypothesis", "metric_name", "evaluator_id",
                "action_id", "rollback_id", "baseline",
            }
            if required.issubset(proposal_dict):
                proposal = ExperimentProposal(
                    **{k: v for k, v in proposal_dict.items() if k in ExperimentProposal.__dataclass_fields__},
                    source_intent=getattr(intent, "action", "") if intent else "heartbeat",
                )
                decision = self.gate.evaluate(proposal, self.registry)
                self._log_proposal(proposal, decision)
                if not decision.approved:
                    results.append({
                        "type": "experiment",
                        "status": "rejected",
                        "lane": decision.lane.value,
                        "reason": decision.reason,
                    })
                else:
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
                    results.append({
                        "type": "experiment",
                        "status": "completed",
                        "lane": decision.lane.value,
                        "result": asdict(result),
                    })

        return results

    async def handle_intent(self, intent, context: dict) -> dict:
        if getattr(intent, "action", "") not in {"research", "develop_skill"}:
            return {"status": "ignored", "reason": "intent is not experimental"}
        direct = self._direct_action(intent, context)
        if direct is not None:
            return await self._run_direct(direct)
        proposal = self._propose(intent, context)
        if proposal is None:
            return {"status": "no_action", "reason": "no executable action in context"}
        decision = self.gate.evaluate(proposal, self.registry)
        self._log_proposal(proposal, decision)
        if not decision.approved:
            return {
                "status": "rejected",
                "lane": decision.lane.value,
                "reason": decision.reason,
                "proposal": asdict(proposal),
            }
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
        return {
            "status": "completed",
            "lane": decision.lane.value,
            "proposal": asdict(proposal),
            "result": asdict(result),
        }

    def _direct_action(self, intent, context: dict) -> ActionRequest | None:
        candidate = context.get("action_candidate")
        if not isinstance(candidate, dict) or not {"name", "action_id"}.issubset(candidate):
            return None
        values = dict(candidate)
        values["source_intent"] = getattr(intent, "action", "")
        return ActionRequest(**values)

    def _propose(self, intent, context: dict) -> ExperimentProposal | None:
        candidate = context.get("experiment_candidate")
        if not isinstance(candidate, dict):
            return None
        required = {
            "name", "hypothesis", "metric_name", "evaluator_id",
            "action_id", "rollback_id", "baseline",
        }
        if not required.issubset(candidate):
            return None
        values = {key: candidate[key] for key in required}
        for key in (
            "lower_is_better", "minimum_improvement", "budget_seconds",
            "risk", "side_effects", "external", "reversible",
            "costs_money", "privacy_sensitive", "affects_others",
        ):
            if key in candidate:
                values[key] = candidate[key]
        values["source_intent"] = getattr(intent, "action", "")
        return ExperimentProposal(**values)

    async def _run_direct(self, request: ActionRequest) -> dict:
        decision = self.gate.classify(request)
        if not decision.approved:
            return {
                "status": "rejected",
                "lane": decision.lane.value,
                "reason": decision.reason,
                "action": asdict(request),
            }
        action = self.registry.actions.get(request.action_id)
        if action is None:
            return {
                "status": "unavailable",
                "lane": decision.lane.value,
                "reason": f"missing action adapter: {request.action_id}",
            }
        await self._call(action)
        try:
            if self.memory is not None and hasattr(self.memory, "store"):
                await self.memory.store(
                    f"Autonomous action {request.name}: completed; {request.reason}",
                    category="autonomy",
                    importance=5,
                    tags=["autonomy", request.source_intent, decision.lane.value],
                )
        except Exception as e:
            logger.warning(f"Action done but memory recording failed: {e}")
        return {"status": "completed", "lane": decision.lane.value, "action": asdict(request)}

    async def _remember(self, proposal: ExperimentProposal, result: ExperimentResult) -> None:
        if self.memory is None or not hasattr(self.memory, "store"):
            return
        try:
            await self.memory.store(
                (
                    f"Autonomous experiment {proposal.name}: {result.status}; "
                    f"{proposal.metric_name} {result.baseline} -> {result.measured}; "
                    f"improvement={result.improvement}; {result.note}"
                ),
                category="experiment",
                importance=7,
                tags=["autonomy", proposal.source_intent, result.status],
            )
        except Exception as e:
            logger.warning(f"Experiment done but memory recording failed: {e}")

    def _log_proposal(self, proposal: ExperimentProposal, decision: GateDecision) -> None:
        self.proposal_log_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "proposal": asdict(proposal),
            "decision": {**asdict(decision), "lane": decision.lane.value},
            "recorded_at": time.time(),
        }
        with self.proposal_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    async def _call(fn):
        value = fn()
        if hasattr(value, "__await__"):
            return await value
        return value
