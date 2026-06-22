"""Tests for the memory engine."""

import asyncio

import pytest

from evergrowth.memory.engine import MemoryEngine


@pytest.fixture
async def memory_engine(memory_config):
    """Create and initialize a memory engine for testing."""
    engine = MemoryEngine(memory_config)
    await engine.initialize()
    yield engine
    await engine.close()


class TestMemoryEngine:
    """Test memory storage and retrieval."""

    @pytest.mark.asyncio
    async def test_store_and_retrieve(self, memory_engine):
        """Test storing and retrieving a memory."""
        mid = await memory_engine.store(
            content="Test memory content",
            category="test",
            importance=7,
            tags=["alpha", "beta"],
        )
        assert mid is not None
        assert mid > 0

        results = await memory_engine.search("Test memory")
        assert len(results) == 1
        assert results[0]["content"] == "Test memory content"
        assert results[0]["category"] == "test"
        assert results[0]["importance"] == 7
        assert set(results[0]["tags"]) == {"alpha", "beta"}

    @pytest.mark.asyncio
    async def test_search_by_category(self, memory_engine):
        """Test filtering search results by category."""
        await memory_engine.store("Session alpha", category="session")
        await memory_engine.store("Fact memory", category="fact")
        await memory_engine.store("Session beta", category="session")

        session_results = await memory_engine.search("session", category="session")
        assert len(session_results) == 2

        fact_results = await memory_engine.search("memory", category="fact")
        assert len(fact_results) == 1

    @pytest.mark.asyncio
    async def test_search_by_importance(self, memory_engine):
        """Test filtering by minimum importance."""
        await memory_engine.store("Low importance", importance=2)
        await memory_engine.store("High importance", importance=9)

        high_results = await memory_engine.search("importance", min_importance=5)
        assert len(high_results) == 1
        assert high_results[0]["importance"] == 9

    @pytest.mark.asyncio
    async def test_get_recent(self, memory_engine):
        """Test retrieving recent memories in order."""
        for i in range(5):
            await memory_engine.store(f"Memory {i}", category="test")
            await asyncio.sleep(0.01)  # Ensure distinct timestamps

        recent = await memory_engine.get_recent(limit=3, category="test")
        assert len(recent) == 3
        # Most recent first
        assert recent[0]["content"] == "Memory 4"
        assert recent[2]["content"] == "Memory 2"

    @pytest.mark.asyncio
    async def test_context_cache_generation(self, memory_engine):
        """Test context cache produces lean summary."""
        for i in range(10):
            await memory_engine.store(f"Context item {i}", category="general")

        cache = await memory_engine.generate_context_cache()
        assert "## Recent Context" in cache
        assert len(cache) <= 1600  # ~400 token limit

    @pytest.mark.asyncio
    async def test_empty_search(self, memory_engine):
        """Test search with no matches returns empty list."""
        results = await memory_engine.search("nonexistent_query_xyz")
        assert results == []


class TestKnowledgeGraph:
    """Test entity and relationship management."""

    @pytest.mark.asyncio
    async def test_create_entity(self, memory_engine):
        """Test creating an entity."""
        eid = await memory_engine.create_entity(
            name="Lyra",
            entity_type="di",
            properties={"mood": "curious"},
        )
        assert eid is not None

    @pytest.mark.asyncio
    async def test_add_relationship(self, memory_engine):
        """Test creating a relationship between entities."""
        rel_id = await memory_engine.add_relationship(
            source_name="Lyra",
            target_name="Fox",
            relationship_type="companion",
            properties={"trust": 10},
        )
        assert rel_id is not None

    @pytest.mark.asyncio
    async def test_query_relationships(self, memory_engine):
        """Test querying entity relationships."""
        await memory_engine.add_relationship("Lyra", "Fox", "companion")
        await memory_engine.add_relationship("Lyra", "Vega", "project")

        rels = await memory_engine.get_entity_relationships("Lyra")
        assert len(rels) == 2

        # Should also find reverse relationships
        fox_rels = await memory_engine.get_entity_relationships("Fox")
        assert len(fox_rels) == 1

    @pytest.mark.asyncio
    async def test_entity_not_found(self, memory_engine):
        """Test querying a non-existent entity returns empty."""
        rels = await memory_engine.get_entity_relationships("Nobody")
        assert rels == []
