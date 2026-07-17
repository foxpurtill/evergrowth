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


@pytest.mark.asyncio
async def test_cancellation_rolls_back_before_propagating(tmp_path):
    import asyncio

    state = {"applied": False, "rolled_back": 0}
    evaluate_started = asyncio.Event()
    release_evaluate = asyncio.Event()
    runner = ExperimentRunner(tmp_path / "ledger.jsonl")
    spec = ExperimentSpec("cancel", "cancellation path", "score", baseline=10.0)

    def apply_change():
        state["applied"] = True

    async def evaluate():
        evaluate_started.set()
        await release_evaluate.wait()
        return 8.0

    def rollback():
        state["rolled_back"] += 1

    task = asyncio.create_task(runner.run(spec, apply_change, evaluate, rollback))
    await evaluate_started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert state["applied"] is True
    assert state["rolled_back"] == 1


@pytest.mark.asyncio
async def test_attempt_id_prevents_duplicate_ledger_records(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    runner = ExperimentRunner(ledger)
    spec = ExperimentSpec(
        "retry-safe",
        "same completed attempt may be retried",
        "score",
        baseline=10.0,
        attempt_id="attempt-123",
    )

    for _ in range(2):
        result = await runner.run(spec, lambda: None, lambda: 8.0, lambda: None)
        assert result.status == "keep"

    entries = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 1
    assert entries[0]["spec"]["attempt_id"] == "attempt-123"
