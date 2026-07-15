"""Bounded autonomous experimentation."""

from .coordinator import (
    AutonomyCoordinator,
    ExperimentAuthorityGate,
    ExperimentProposal,
    ExperimentRegistry,
    GateDecision,
)
from .mission import (
    EvaluatorLibrary,
    LearningGovernor,
    Priority,
    PriorityBoard,
    TelemetryProposalGenerator,
    TelemetrySignal,
)
from .runner import ExperimentResult, ExperimentRunner, ExperimentSpec

__all__ = [
    "AutonomyCoordinator",
    "ExperimentAuthorityGate",
    "ExperimentProposal",
    "ExperimentRegistry",
    "GateDecision",
    "EvaluatorLibrary",
    "LearningGovernor",
    "Priority",
    "PriorityBoard",
    "TelemetryProposalGenerator",
    "TelemetrySignal",
    "ExperimentResult",
    "ExperimentRunner",
    "ExperimentSpec",
]
