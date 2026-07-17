"""Self-improving skills registry for Evergrowth."""

import json
import logging
import time

logger = logging.getLogger("evergrowth.skills")


class Skill:
    """Represents a learned skill."""

    def __init__(self, data: dict):
        self.id = data.get("id", "")
        self.name = data.get("name", "")
        self.description = data.get("description", "")
        self.steps = data.get("steps", [])
        self.category = data.get("category", "general")
        self.version = data.get("version", 1)
        self.uses = data.get("uses", 0)
        self.created_at = data.get("created_at", time.time())
        self.updated_at = data.get("updated_at", time.time())
        self.success_rate = data.get("success_rate", 1.0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "category": self.category,
            "version": self.version,
            "uses": self.uses,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "success_rate": self.success_rate,
        }


class SkillRegistry:
    """
    Manages the DI's learned skills.

    Skills are:
    - Created automatically after complex tasks
    - Versioned and improved during use
    - Searchable by name, category, or content
    - Persisted to disk as JSON
    """

    def __init__(self, config):
        self.config = config
        self.skills_path = config.resolve_skills_path()
        self._skills: dict[str, Skill] = {}

    async def initialize(self):
        """Load existing skills from disk."""
        self.skills_path.mkdir(parents=True, exist_ok=True)
        self._load_skills()
        logger.info(f"Skills registry initialized: {len(self._skills)} skills loaded")

    def _load_skills(self):
        """Load all skill files from disk."""
        for skill_file in self.skills_path.glob("*.json"):
            try:
                with open(skill_file, encoding="utf-8") as f:
                    data = json.load(f)
                skill = Skill(data)
                self._skills[skill.id] = skill
            except Exception as e:
                logger.warning(f"Failed to load skill {skill_file}: {e}")

    def _save_skill(self, skill: Skill):
        """Save a skill atomically."""
        skill_file = self.skills_path / f"{skill.id}.json"
        temporary = skill_file.with_suffix(skill_file.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(skill.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary.replace(skill_file)
        except Exception as e:
            temporary.unlink(missing_ok=True)
            logger.error(f"Failed to save skill {skill.name}: {e}")

    async def list(self, category: str | None = None) -> list[dict]:
        """List all skills, optionally filtered by category."""
        skills = list(self._skills.values())
        if category:
            skills = [s for s in skills if s.category == category]
        return [s.to_dict() for s in skills]

    async def get(self, skill_id: str) -> dict | None:
        """Get a specific skill by ID."""
        skill = self._skills.get(skill_id)
        return skill.to_dict() if skill else None

    async def create(
        self,
        name: str,
        description: str,
        steps: list[str],
        category: str = "general",
    ) -> str:
        """Create a new skill. Returns the skill ID."""
        import hashlib
        skill_id = hashlib.sha256(f"{name}:{time.time()}".encode()).hexdigest()[:12]

        skill = Skill({
            "id": skill_id,
            "name": name,
            "description": description,
            "steps": steps,
            "category": category,
            "version": 1,
            "uses": 0,
            "created_at": time.time(),
            "updated_at": time.time(),
            "success_rate": 1.0,
        })

        self._skills[skill_id] = skill
        self._save_skill(skill)
        logger.info(f"Created skill: {name} (v{skill.version})")
        return skill_id

    async def update(
        self,
        skill_id: str,
        steps: list[str] | None = None,
        description: str | None = None,
    ) -> bool:
        """Update an existing skill (creates new version)."""
        skill = self._skills.get(skill_id)
        if not skill:
            return False

        skill.version += 1
        skill.updated_at = time.time()

        if steps is not None:
            skill.steps = steps
        if description is not None:
            skill.description = description

        self._save_skill(skill)
        logger.info(f"Updated skill: {skill.name} (v{skill.version})")
        return True

    async def record_use(self, skill_id: str, success: bool = True):
        """Record a use of a skill (for self-improvement tracking)."""
        skill = self._skills.get(skill_id)
        if not skill:
            return

        skill.uses += 1
        # Update success rate with exponential moving average
        alpha = 0.3
        skill.success_rate = alpha * (1.0 if success else 0.0) + (1 - alpha) * skill.success_rate
        skill.updated_at = time.time()

        self._save_skill(skill)

    async def search(self, query: str) -> list[dict]:
        """Search skills by name or description."""
        query_lower = query.lower()
        results = []
        for skill in self._skills.values():
            if (
                query_lower in skill.name.lower()
                or query_lower in skill.description.lower()
                or any(query_lower in step.lower() for step in skill.steps)
            ):
                results.append(skill.to_dict())
        return results

    async def auto_create_from_task(
        self,
        task_name: str,
        steps: list[str],
        category: str = "auto",
    ) -> str | None:
        """Automatically create a skill from a completed task."""
        if not self.config.skills.auto_create:
            return None

        # Check if a similar skill already exists
        existing = await self.search(task_name)
        if existing:
            # Update existing skill instead of creating new
            await self.update(existing[0]["id"], steps=steps)
            return existing[0]["id"]

        return await self.create(
            name=task_name,
            description=f"Auto-created skill from task: {task_name}",
            steps=steps,
            category=category,
        )
