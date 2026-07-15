"""Bounded autonomous experimentation."""

from .coordinator import (
    AutonomyCoordinator,
    ExperimentAuthorityGate,
    ExperimentProposal,
    ExperimentRegistry,
    GateDecision,
)
from .runner import ExperimentResult, ExperimentRunner, ExperimentSpec

__all__ = [
    "AutonomyCoordinator",
    "ExperimentAuthorityGate",
    "ExperimentProposal",
    "ExperimentRegistry",
    "GateDecision",
    "ExperimentResult",
    "ExperimentRunner",
    "ExperimentSpec",
]
