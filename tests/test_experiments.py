"""Tests for bounded autonomous experiments."""

import json

import pytest

from evergrowth.experiments import ExperimentRunner, ExperimentSpec


@pytest.mark.asyncio
async def test_keeps_improvement(tmp_path):
    state = {"changed": False, "rolled_back": False}
    runner = ExperimentRunner(tmp_path / "ledger.jsonl")
    spec = ExperimentSpec("better", "improves score", "score", baseline=10.0)

    result = await runner.run(
        spec,
        lambda: state.update(changed=True),
        lambda: 8.0,
        lambda: state.update(rolled_back=True),
    )

    assert result.status == "keep"
    assert state == {"changed": True, "rolled_back": False}


@pytest.mark.asyncio
async def test_discards_regression_and_logs(tmp_path):
    state = {"rolled_back": False}
    ledger = tmp_path / "ledger.jsonl"
    runner = ExperimentRunner(ledger)
    spec = ExperimentSpec("worse", "may regress", "score", baseline=10.0)

    result = await runner.run(
        spec,
        lambda: None,
        lambda: 11.0,
        lambda: state.update(rolled_back=True),
    )

    assert result.status == "discard"
    assert state["rolled_back"] is True
    entry = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert entry["result"]["status"] == "discard"


@pytest.mark.asyncio
async def test_crash_rolls_back(tmp_path):
    state = {"rolled_back": False}
    runner = ExperimentRunner(tmp_path / "ledger.jsonl")
    spec = ExperimentSpec("crash", "failure path", "score", baseline=10.0)

    def explode():
        raise RuntimeError("boom")

    result = await runner.run(
        spec,
        lambda: None,
        explode,
        lambda: state.update(rolled_back=True),
    )

    assert result.status == "crash"
    assert state["rolled_back"] is True
