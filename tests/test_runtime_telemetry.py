import json

import pytest

from evergrowth.telemetry import (
    DeploymentVerifier,
    RegressionDetector,
    TelemetryEvent,
    TelemetryStore,
)


def test_telemetry_store_roundtrip(tmp_path):
    path = tmp_path / "telemetry.jsonl"
    store = TelemetryStore(path)
    store.record(TelemetryEvent("duplicate_rate", 0.25, "discord"))
    events = store.recent("duplicate_rate")
    assert len(events) == 1
    assert events[0].source == "discord"
    assert events[0].value == 0.25


def test_regression_detector_detects_worse_metric():
    detector = RegressionDetector(tolerance=0.05, lower_is_better=True)
    regression = detector.detect("duplicate_rate", 0.1, [0.2, 0.22])
    assert regression is not None
    assert regression.current == pytest.approx(0.21)
    assert regression.delta > 0.1


def test_regression_detector_ignores_small_change():
    detector = RegressionDetector(tolerance=0.05, lower_is_better=True)
    assert detector.detect("latency", 1.0, [1.02, 1.03]) is None


def test_deployment_verifier_marks_and_verifies(tmp_path, monkeypatch):
    marker = tmp_path / "running.json"
    verifier = DeploymentVerifier(tmp_path, marker)
    monkeypatch.setattr(verifier, "current_commit", lambda: "abc123")
    marked = verifier.mark_running()
    assert marked.status == "verified"
    assert json.loads(marker.read_text())["observed_commit"] == "abc123"

    mismatch = verifier.verify("def456")
    assert mismatch.status == "version_mismatch"
