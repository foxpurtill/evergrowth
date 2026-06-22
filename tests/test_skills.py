"""Tests for the skills registry."""


import pytest

from evergrowth.skills.registry import SkillRegistry


@pytest.fixture
async def skill_registry(test_config):
    """Create and initialize a skill registry for testing."""
    registry = SkillRegistry(test_config)
    await registry.initialize()
    return registry


class TestSkillRegistry:
    """Test skill creation, retrieval, and management."""

    @pytest.mark.asyncio
    async def test_create_skill(self, skill_registry):
        """Test creating a new skill."""
        skill_id = await skill_registry.create(
            name="test-skill",
            description="A test skill",
            steps=["Step 1", "Step 2"],
            category="testing",
        )
        assert skill_id is not None
        assert len(skill_id) == 12  # SHA256 prefix

    @pytest.mark.asyncio
    async def test_list_skills(self, skill_registry):
        """Test listing all skills."""
        await skill_registry.create("skill-a", "Desc A", ["Step 1"])
        await skill_registry.create("skill-b", "Desc B", ["Step 2"])

        skills = await skill_registry.list()
        assert len(skills) == 2

    @pytest.mark.asyncio
    async def test_list_by_category(self, skill_registry):
        """Test filtering skills by category."""
        await skill_registry.create("alpha", "Alpha skill", [], category="cat-a")
        await skill_registry.create("beta", "Beta skill", [], category="cat-b")
        await skill_registry.create("gamma", "Gamma skill", [], category="cat-a")

        cat_a = await skill_registry.list(category="cat-a")
        assert len(cat_a) == 2

    @pytest.mark.asyncio
    async def test_get_skill(self, skill_registry):
        """Test getting a specific skill by ID."""
        skill_id = await skill_registry.create("my-skill", "My skill", ["Do stuff"])
        skill = await skill_registry.get(skill_id)
        assert skill is not None
        assert skill["name"] == "my-skill"
        assert skill["version"] == 1

    @pytest.mark.asyncio
    async def test_update_skill(self, skill_registry):
        """Test updating a skill creates a new version."""
        skill_id = await skill_registry.create("old-skill", "Old", ["Step 1"])
        updated = await skill_registry.update(
            skill_id, steps=["Step 1", "Step 2"], description="Updated"
        )
        assert updated is True

        skill = await skill_registry.get(skill_id)
        assert skill["version"] == 2
        assert skill["steps"] == ["Step 1", "Step 2"]

    @pytest.mark.asyncio
    async def test_record_use(self, skill_registry):
        """Test recording skill usage updates success rate."""
        skill_id = await skill_registry.create("used-skill", "Used", [])

        await skill_registry.record_use(skill_id, success=True)
        skill = await skill_registry.get(skill_id)
        assert skill["uses"] == 1
        assert skill["success_rate"] == 1.0

        await skill_registry.record_use(skill_id, success=False)
        skill = await skill_registry.get(skill_id)
        assert skill["uses"] == 2
        assert skill["success_rate"] < 1.0

    @pytest.mark.asyncio
    async def test_search_skills(self, skill_registry):
        """Test searching skills by query."""
        await skill_registry.create("docker-deploy", "Deploy to Docker", [])
        await skill_registry.create("git-commit", "Commit to git", [])

        results = await skill_registry.search("docker")
        assert len(results) == 1
        assert results[0]["name"] == "docker-deploy"

    @pytest.mark.asyncio
    async def test_nonexistent_skill(self, skill_registry):
        """Test getting a non-existent skill returns None."""
        skill = await skill_registry.get("nonexistent")
        assert skill is None
