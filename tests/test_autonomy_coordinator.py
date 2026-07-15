import json

import pytest

from evergrowth.experiments import (
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
    assert result["result"]["status"] == "keep"
    assert memory.items and "brief dedup" in memory.items[0][0]


@pytest.mark.asyncio
async def test_rejects_unregistered_or_external_side_effects(tmp_path):
    coordinator = AutonomyCoordinator(ExperimentRunner(tmp_path / "ledger.jsonl"))
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
                "side_effects": ["external_message"],
            }
        },
    )
    assert result["status"] == "rejected"
    proposal_log = tmp_path / "experiment_proposals.jsonl"
    entry = json.loads(proposal_log.read_text(encoding="utf-8").splitlines()[0])
    assert entry["gate"]["approved"] is False


@pytest.mark.asyncio
async def test_non_experimental_intent_is_ignored(tmp_path):
    coordinator = AutonomyCoordinator(ExperimentRunner(tmp_path / "ledger.jsonl"))
    result = await coordinator.handle_intent(intent("check_in"), {})
    assert result["status"] == "ignored"
