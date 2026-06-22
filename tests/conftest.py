"""Shared test fixtures for Evergrowth."""

import tempfile
from pathlib import Path

import pytest

from evergrowth.core.config import (
    EvergrowthConfig,
    HeartbeatConfig,
    IdentityConfig,
    MCPConfig,
    MemoryConfig,
    SchedulerConfig,
    SkillsConfig,
)


@pytest.fixture
def tmp_dir():
    """Provide a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def test_config(tmp_dir):
    """Create a test configuration using temp directories."""
    return EvergrowthConfig(
        di_name="TestDI",
        di_letter="T",
        data_dir=str(tmp_dir / "data"),
        heartbeat=HeartbeatConfig(enabled=False),
        memory=MemoryConfig(db_path=str(tmp_dir / "data" / "memory.db")),
        skills=SkillsConfig(skills_path=str(tmp_dir / "data" / "skills")),
        identity=IdentityConfig(soul_path=str(tmp_dir / "soul")),
        mcp=MCPConfig(),
        scheduler=SchedulerConfig(enabled=False),
    )


@pytest.fixture
def memory_config(tmp_dir):
    """Create a memory-only test configuration."""
    return EvergrowthConfig(
        di_name="TestDI",
        data_dir=str(tmp_dir / "data"),
        memory=MemoryConfig(db_path=str(tmp_dir / "data" / "memory.db")),
    )
