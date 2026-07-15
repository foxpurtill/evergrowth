import json

import pytest

from evergrowth.experiments import (
    ActionLane,
    AutonomyCoordinator,
    ExperimentRegistry,
    ExperimentRunner,
)
from evergrowth.selfprompt.engine import Intent, OutreachGate


class MemoryStub:
    def __init__(self):
        self.items = []

    async def store(self, content, **kwargs):
        self.items.append((content, kwargs))
        return 1


def intent(action="research"):
    return Intent(action, "test", 0.2, OutreachGate.RESEARCH)


@pytest.mark.asyncio
async def test_runs_approved_proposal_and_remembers(tmp_path):
    state = {"score": 10.0, "old": 10.0}
    registry = ExperimentRegistry()
    registry.register_action("improve", lambda: state.update(score=8.0))
    registry.register_evaluator("score", lambda: state["score"])
    registry.register_rollback("undo", lambda: state.update(score=state["old"]))
    memory = MemoryStub()
    coordinator = AutonomyCoordinator(
        ExperimentRunner(tmp_path / "ledger.jsonl"), memory=memory, registry=registry
    )
    result = await coordinator.handle_intent(
        intent(),
        {
            "experiment_candidate": {
                "name": "brief dedup",
                "hypothesis": "duplicates fall",
                "metric_name": "duplicates",
                "evaluator_id": "score",
                "action_id": "improve",
                "rollback_id": "undo",
                "baseline": 10.0,
                "minimum_improvement": 1.0,
                "side_effects": ["local_files"],
            }
        },
    )
    assert result["status"] == "completed"
    assert result["lane"] == ActionLane.ACT.value
    assert result["result"]["status"] == "keep"
    assert memory.items and "brief dedup" in memory.items[0][0]


@pytest.mark.asyncio
async def test_consequential_boundary_asks_even_when_executable(tmp_path):
    registry = ExperimentRegistry()
    registry.register_action("post", lambda: None)
    registry.register_evaluator("clicks", lambda: 1.0)
    registry.register_rollback("delete", lambda: None)
    coordinator = AutonomyCoordinator(
        ExperimentRunner(tmp_path / "ledger.jsonl"), registry=registry
    )
    result = await coordinator.handle_intent(
        intent(),
        {
            "experiment_candidate": {
                "name": "publish",
                "hypothesis": "engagement rises",
                "metric_name": "clicks",
                "evaluator_id": "clicks",
                "action_id": "post",
                "rollback_id": "delete",
                "baseline": 0.0,
                "risk": "high",
                "external": True,
                "affects_others": True,
                "side_effects": ["external_message"],
            }
        },
    )
    assert result["status"] == "rejected"
    proposal_log = tmp_path / "experiment_proposals.jsonl"
    entry = json.loads(proposal_log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["decision"]["approved"] is False
    assert entry["decision"]["lane"] == ActionLane.ASK.value


@pytest.mark.asyncio
async def test_reversible_live_work_acts_and_reports(tmp_path):
    registry = ExperimentRegistry()
    registry.register_action("restart", lambda: None)
    registry.register_evaluator("health", lambda: 0.0)
    registry.register_rollback("undo", lambda: None)
    coordinator = AutonomyCoordinator(
        ExperimentRunner(tmp_path / "ledger.jsonl"), registry=registry
    )
    result = await coordinator.handle_intent(
        intent(),
        {
            "experiment_candidate": {
                "name": "restart worker",
                "hypothesis": "health improves",
                "metric_name": "health",
                "evaluator_id": "health",
                "action_id": "restart",
                "rollback_id": "undo",
                "baseline": 1.0,
                "external": True,
                "reversible": True,
                "side_effects": ["service_restart"],
            }
        },
    )
    assert result["status"] == "completed"
    assert result["lane"] == ActionLane.ACT_AND_REPORT.value


@pytest.mark.asyncio
async def test_internal_direct_action_runs_without_experiment_ceremony(tmp_path):
    state = {"ran": False}
    registry = ExperimentRegistry()
    registry.register_action("organize", lambda: state.update(ran=True))
    memory = MemoryStub()
    coordinator = AutonomyCoordinator(
        ExperimentRunner(tmp_path / "ledger.jsonl"), memory=memory, registry=registry
    )
    result = await coordinator.handle_intent(
        intent(),
        {
            "action_candidate": {
                "name": "organize notes",
                "action_id": "organize",
                "reason": "reduce clutter",
                "side_effects": ["local_files"],
            }
        },
    )
    assert result["status"] == "completed"
    assert result["lane"] == ActionLane.ACT.value
    assert state["ran"] is True
    assert memory.items and "organize notes" in memory.items[0][0]


@pytest.mark.asyncio
async def test_direct_action_stops_only_at_consequential_boundary(tmp_path):
    registry = ExperimentRegistry()
    registry.register_action("send", lambda: None)
    coordinator = AutonomyCoordinator(
        ExperimentRunner(tmp_path / "ledger.jsonl"), registry=registry
    )
    result = await coordinator.handle_intent(
        intent(),
        {
            "action_candidate": {
                "name": "send external message",
                "action_id": "send",
                "external": True,
                "affects_others": True,
                "reversible": False,
            }
        },
    )
    assert result["status"] == "rejected"
    assert result["lane"] == ActionLane.ASK.value


@pytest.mark.asyncio
async def test_non_experimental_intent_is_ignored(tmp_path):
    coordinator = AutonomyCoordinator(ExperimentRunner(tmp_path / "ledger.jsonl"))
    result = await coordinator.handle_intent(intent("check_in"), {})
    assert result["status"] == "ignored"
