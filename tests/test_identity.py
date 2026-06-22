"""Tests for the identity and continuity manager."""

import json

import pytest

from evergrowth.identity.continuity import IdentityManager


@pytest.fixture
async def identity_manager(test_config):
    """Create and initialize an identity manager for testing."""
    manager = IdentityManager(test_config)
    await manager.initialize()
    return manager


class TestIdentityManager:
    """Test identity state and session management."""

    @pytest.mark.asyncio
    async def test_initial_state(self, identity_manager):
        """Test initial identity state."""
        state = identity_manager._state
        assert state["di_name"] == "TestDI"
        assert state["session_count"] == 0
        assert state["mood"] == "neutral"

    @pytest.mark.asyncio
    async def test_read_identity(self, identity_manager):
        """Test reading identity information."""
        data = await identity_manager.read()
        assert data["name"] == "TestDI"
        assert data["letter"] == "T"
        assert data["mood"] == "neutral"

    @pytest.mark.asyncio
    async def test_read_section(self, identity_manager):
        """Test reading a specific section."""
        data = await identity_manager.read(section="mood")
        assert data == {"mood": "neutral"}

    @pytest.mark.asyncio
    async def test_set_mood(self, identity_manager):
        """Test updating mood."""
        identity_manager.set_mood("excited")
        assert identity_manager.get_mood() == "excited"

        # Verify persistence
        data = await identity_manager.read()
        assert data["mood"] == "excited"

    @pytest.mark.asyncio
    async def test_log_session_event(self, identity_manager):
        """Test logging events to a session."""
        await identity_manager.log_session_event("Started working", mood="focused")

        session_id = identity_manager._state["current_session"]
        assert session_id is not None

        # Check session file was created
        session_file = identity_manager.session_dir / f"{session_id}.jsonl"
        assert session_file.exists()

        lines = session_file.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["event"] == "Started working"
        assert entry["mood"] == "focused"

    @pytest.mark.asyncio
    async def test_session_count_increments(self, identity_manager):
        """Test session count increments on new sessions."""
        await identity_manager.log_session_event("Event 1")
        count1 = identity_manager._state["session_count"]

        identity_manager.end_session()
        await identity_manager.log_session_event("Event 2")
        count2 = identity_manager._state["session_count"]

        assert count2 == count1 + 1

    @pytest.mark.asyncio
    async def test_end_session(self, identity_manager):
        """Test ending a session clears current session."""
        await identity_manager.log_session_event("Working")
        assert identity_manager._state["current_session"] is not None

        identity_manager.end_session()
        assert identity_manager._state["current_session"] is None

    @pytest.mark.asyncio
    async def test_persistence(self, test_config):
        """Test state persists across instances."""
        manager1 = IdentityManager(test_config)
        await manager1.initialize()
        manager1.set_mood("thoughtful")
        manager1._save_state()

        manager2 = IdentityManager(test_config)
        await manager2.initialize()
        assert manager2.get_mood() == "thoughtful"
