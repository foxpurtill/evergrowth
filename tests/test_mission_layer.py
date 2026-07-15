import json

import pytest

from evergrowth.experiments import (
    EvaluatorLibrary,
    LearningGovernor,
    Priority,
    PriorityBoard,
    TelemetryProposalGenerator,
    TelemetrySignal,
)


def test_priority_board_persists_and_ranks(tmp_path):
    board = PriorityBoard(tmp_path / "priorities.json")
    board.save(
        [
            Priority("paused", "Paused", status="paused", weight=9),
            Priority("reliability", "Reliability", weight=3),
            Priority("briefs", "Brief quality", weight=1),
        ]
    )
    assert [item.key for item in board.active()] == ["reliability", "briefs"]


def test_evaluator_library_metrics():
    events = [{"dedup_key": "a"}, {"dedup_key": "a"}, {"dedup_key": "b"}]
    assert EvaluatorLibrary.duplicate_rate(events) == pytest.approx(1 / 3)
    assert EvaluatorLibrary.error_rate([{"status": "ok"}, {"status": "error"}]) == 0.5


def test_governor_does_not_duplicate_priority_permission(tmp_path):
    governor = LearningGovernor(tmp_path / "ledger.jsonl")
    proposal = type("P", (), {"name": "x", "metric_name": "duplicates"})()
    allowed, reason = governor.evaluate(proposal, Priority("x", "X", status="paused"))
    assert allowed
    assert "learning budget" in reason


def test_governor_detects_plateau(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    entries = [
        {"spec": {"name": "dedup"}, "result": {"status": "discard"}},
        {"spec": {"name": "dedup"}, "result": {"status": "crash"}},
    ]
    ledger.write_text("\n".join(json.dumps(item) for item in entries), encoding="utf-8")
    governor = LearningGovernor(ledger, max_attempts_per_name=5)
    proposal = type("P", (), {"name": "dedup", "metric_name": "duplicates"})()
    priority = Priority("reliability", "Reliability", allowed_metrics=["duplicates"])
    allowed, reason = governor.evaluate(proposal, priority)
    assert not allowed
    assert "plateau" in reason


def test_generator_selects_highest_weight_active_signal(tmp_path):
    board = PriorityBoard(tmp_path / "priorities.json")
    board.save(
        [
            Priority("reliability", "Reliability", weight=4, allowed_metrics=["duplicates"]),
            Priority("briefs", "Briefs", weight=1, allowed_metrics=["repetition"]),
        ]
    )
    generator = TelemetryProposalGenerator(board, LearningGovernor(tmp_path / "ledger.jsonl"))
    signals = [
        TelemetrySignal(
            "brief-repeat", "repetition", 0.8, "e1", "a1", "r1", "briefs", "reduce repetition"
        ),
        TelemetrySignal(
            "presence-dedup",
            "duplicates",
            0.4,
            "e2",
            "a2",
            "r2",
            "reliability",
            "reduce duplicates",
        ),
    ]
    proposal, reason = generator.generate(signals)
    assert proposal.name == "presence-dedup"
    assert "learning budget" in reason
