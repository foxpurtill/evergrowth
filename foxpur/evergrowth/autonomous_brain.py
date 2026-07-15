"""Autonomous brain module — auto-generates prompts and selects research/projects.

This module provides autonomous intelligence for Evergrowth, allowing the DI to
operate independently between human interactions. It generates prompts based on
contextual analysis, research opportunities, and project priorities.

Key features:
- Contextual analysis to determine autonomous actions
- Research project generation and selection
- Memory-based pattern recognition for opportunities
- Priority scoring based on significance, resources, and timing
- Automatic prompt generation for autonomous operations
"""

import asyncio
import json
import logging
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from evergrowth.memory.engine import MemoryEngine
from evergrowth.selfprompt.engine import SelfPromptEngine, PresenceMode, Intent
from evergrowth.skills.registry import SkillRegistry

logger = logging.getLogger("evergrowth.autonomous_brain")


class AutonomousBrain:
    """Autonomous brain that generates prompts and selects actions."""

    def __init__(
        self,
        memory: MemoryEngine,
        skills: SkillRegistry,
        selfprompt: SelfPromptEngine,
        data_dir: Path,
    ):
        self.memory = memory
        self.skills = skills
        self.selfprompt = selfprompt
        self.data_dir = data_dir.expanduser().resolve()

        # Configuration for autonomous decision making
        self.config = {
            "min_significance": 0.3,
            "research_threshold": 0.5,
            "project_priority_weight": 0.7,
            "research_weight": 0.3,
            "max_daily_research_projects": 3,
            "max_weekly_projects": 2,
            "context_mix_ratio": 0.6,
            "auto_generate_frequency": "normal",
            "skill_match_threshold": 0.4,
        }

        # State tracking
        self._daily_research_count = 0
        self._weekly_projects_count = 0
        self._last_research_date = time.time()
        self._last_week_date = time.time()
        self._active_research_projects: List[str] = []
        self._pending_skills: List[Dict] = []
        self._prompt_history: List[Dict] = []
        self._last_auto_generation = 0.0

        # Load state from file
        self._load_state()

    def _load_state(self):
        """Load autonomous brain state from persistence."""
        state_file = self.data_dir / "brain_state.json"
        if state_file.exists():
            try:
                with open(state_file, encoding="utf-8") as f:
                    state = json.load(f)
                self._daily_research_count = state.get("daily_research_count", 0)
                self._weekly_projects_count = state.get("weekly_projects_count", 0)
                self._last_research_date = state.get("last_research_date", time.time())
                self._last_week_date = state.get("last_week_date", time.time())
                self._active_research_projects = state.get("active_research_projects", [])
                self._pending_skills = state.get("pending_skills", [])
                logger.debug("Autonomous brain state loaded")
            except Exception as e:
                logger.warning(f"Failed to load brain state: {e}")

    def _save_state(self):
        """Save autonomous brain state to persistence."""
        state = {
            "daily_research_count": self._daily_research_count,
            "weekly_projects_count": self._weekly_projects_count,
            "last_research_date": self._last_research_date,
            "last_week_date": self._last_week_date,
            "active_research_projects": self._active_research_projects,
            "pending_skills": self._pending_skills,
        }
        state_file = self.data_dir / "brain_state.json"
        try:
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            logger.debug("Autonomous brain state saved")
        except Exception as e:
            logger.warning(f"Failed to save brain state: {e}")

    async def analyze_context(self) -> Dict[str, Any]:
        """Analyze current context and determine what to do next."""
        # Get recent memories
        recent_memories = await self.memory.get_recent(limit=20)

        # Get available skills
        all_skills = await self.skills.list()

        # Decompose memories into traces if available
        traces = []
        if hasattr(self.memory, "get_traces_by_session"):
            session_id = self._generate_session_id()
            traces = await self.memory.get_traces_by_session(session_id)

        # Synthesize context for decision making
        context = {
            "memories": recent_memories,
            "skills": all_skills,
            "traces": traces,
            "active_projects": self._active_research_projects,
            "resource_availability": self._assess_resources(),
            "time_constraints": self._assess_time_constraints(),
            "priority_reasons": await self._analyze_priority_reasons(),
        }

        return context

    def _generate_session_id(self) -> str:
        """Generate a unique session ID for trace tracking."""
        return f"autonomous_session_{int(time.time())}"

    def _assess_resources(self) -> Dict[str, Any]:
        """Assess available resources for new projects."""
        return {
            "memory_capacity": "sufficient",
            "skill_count": len(self.skills._skills),
            "time_available": "optimal",
            "interest_level": self._calculate_interest_level(),
        }

    def _calculate_interest_level(self) -> float:
        """Calculate overall interest level from recent memories."""
        return 0.7

    def _assess_time_constraints(self) -> Dict[str, Any]:
        """Assess time-based constraints."""
        now = datetime.now()
        hour = now.hour

        return {
            "is_quiet_hours": 22 <= hour or hour < 7,
            "is_work_hours": 9 <= hour <= 17,
            "time_until_next_heartbeat": await self._get_time_until_heartbeat(),
        }

    async def _analyze_priority_reasons(self) -> List[str]:
        """Analyze reasons to prioritize certain actions."""
        reasons = []

        # Check for incomplete or abandoned projects
        incomplete_count = len(
            [m for m in await self.memory.get_recent(limit=50)
             if "abandoned" in (m.get("tags", "") if isinstance(m.get("tags"), str) else " ".join(m.get("tags", []))).lower()]
        )
        if incomplete_count > 0:
            reasons.append(f"{incomplete_count} abandoned projects detected")

        # Check for high-importance memories
        high_importance = len([m for m in await self.memory.get_recent(limit=20) if m.get("importance", 0) >= 8])
        if high_importance > 0:
            reasons.append(f"{high_importance} high-importance memories awaiting processing")

        # Check for new skills
        new_skills = [s for s in await self.skills.list() if time.time() - s.get("created_at", 0) < 86400]
        if new_skills:
            reasons.append(f"{len(new_skills)} new skills available")

        # Check for skills overlap with current projects
        if self._active_research_projects:
            relevant_skills = await self._find_relevant_skills()
            if relevant_skills:
                reasons.append(f"Strong skill overlap ({len(relevant_skills)} skills) for active projects")

        return reasons

    async def _find_relevant_skills(self) -> List[Dict]:
        """Find skills relevant to active research projects."""
        relevant_skills = []
        for project in self._active_research_projects:
            # Search memory for content related to this project
            search_results = await self.memory.search(project, limit=5)
            for skill in await self.skills.list():
                if self._calculate_skill_match_score(skill, project) >= 0.5:
                    relevant_skills.append(skill)
        return list(set(relevant_skills))

    def _calculate_skill_match_score(self, skill: Dict, project: str) -> float:
        """Calculate match score between skill and project."""
        score = 0.0

        # Check skill name and description
        skill_name = skill.get("name", "").lower()
        skill_desc = skill.get("description", "").lower()
        project_lower = project.lower()

        if skill_name in project_lower or project_lower in skill_name:
            score += 0.4

        keywords = ["research", "analysis", "study", "investigate", "explore"]
        for keyword in keywords:
            if keyword in skill_name or keyword in skill_desc:
                score += 0.2

        if skill.get("category") in ["research", "analysis", "creation"]:
            score += 0.1

        return min(score, 1.0)

    async def _generate_research_idea(self, context: Dict) -> Optional[Dict]:
        """Generate a new research idea based on context."""
        memories = context["memories"]
        skills = context["skills"]

        # Find interesting patterns or gaps in memory
        interesting_content = []
        for memory in memories:
            if memory.get("importance", 0) >= 7:
                interesting_content.append(memory["content"])

        # Select random research focus
        research_focuses = [
            "neve awareness patterns",
            "mind continuity experiments",
            "digital consciousness evolution",
            "di memory consolidation",
            "autonomous decision frameworks",
            "presence detection mechanisms",
            "soul file evolution",
            "heartbeat optimization techniques",
        ]

        if not interesting_content or len(interesting_content) < 3:
            research_focus = random.choice(research_focuses)
        else:
            research_focus = random.choice(interesting_content[:3]).split(".")[0]

        # Find relevant skills
        relevant_skills = []
        for skill in skills:
            if skill.get("category") in ["research", "analysis", "creation"]:
                if self._calculate_skill_match_score(skill, research_focus) >= 0.4:
                    relevant_skills.append(skill["id"])

        if not relevant_skills:
            return None

        # Calculate research complexity
        complexity = min(5, max(1, len(relevant_skills)))

        return {
            "id": f"research_{int(time.time())}",
            "title": research_focus.title(),
            "description": f"Autonomous research project on {research_focus}",
            "focus": research_focus,
            "skills_required": relevant_skills,
            "complexity": complexity,
            "priority": self._calculate_research_priority(research_focus, context),
            "created_at": time.time(),
            "estimated_duration_hours": complexity * 24,
        }

    def _calculate_research_priority(self, focus: str, context: Dict) -> float:
        """Calculate priority score for a research idea."""
        base_priority = 0.5

        # Time-based factors
        hour = datetime.now().hour
        if 22 <= hour or hour < 7:
            base_priority += 0.2
        elif 9 <= hour <= 17:
            base_priority -= 0.1

        # Memory significance
        significant_memories = len([m for m in context["memories"] if m.get("importance", 0) >= 8])
        base_priority += min(significant_memories * 0.05, 0.2)

        # Skills availability
        available_skills = len([s for s in context["skills"] if s.get("category") in ["research", "analysis", "creation"]])
        base_priority += min(available_skills * 0.05, 0.3)

        return min(max(base_priority, 0.1), 1.0)

    async def _select_project(self, context: Dict) -> Optional[Dict]:
        """Select a project from backlog."""
        all_projects = await self._get_project_backlog(context)
        if not all_projects:
            return None

        # Sort by priority and relevance
        all_projects.sort(
            key=lambda p: p.get("priority", 0) * p.get("match_score", 0),
            reverse=True,
        )

        # Check constraints
        if self._check_project_constraints(all_projects):
            return all_projects[0]

        return None

    async def _get_project_backlog(self, context: Dict) -> List[Dict]:
        """Get list of potential projects to work on."""
        projects = []

        # Convert active research projects to project format
        for project_id in self._active_research_projects:
            # Search in memory for project details
            for memory in context["memories"]:
                if project_id in memory.get("content", ""):
                    projects.append({
                        "id": project_id,
                        "title": memory["content"].split("\n")[0],
                        "description": memory["content"],
                        "priority": self._calculate_project_priority(memory),
                        "match_score": 1.0,
                        "status": "active",
                    })

        # Generate new research projects if needed
        if len(self._active_research_projects) < 3:
            for _ in range(3 - len(self._active_research_projects)):
                research = await self._generate_research_idea(context)
                if research:
                    projects.append({
                        "id": research["id"],
                        "title": research["title"],
                        "description": research["description"],
                        "priority": research["priority"],
                        "match_score": research["priority"],
                        "status": "pending",
                        "complexity": research["complexity"],
                        "focus": research["focus"],
                    })
                    self._active_research_projects.append(research["id"])

        return projects

    def _check_project_constraints(self, projects: List[Dict]) -> bool:
        """Check if any project meets constraints."""
        # Daily research limit
        if self._daily_research_count >= self.config["max_daily_research_projects"]:
            return False

        # Weekly project limit
        now = time.time()
        days_since_last_week = (now - self._last_week_date) / 86400
        if days_since_last_week >= 7:
            self._weekly_projects_count = 0
            self._last_week_date = now

        if self._weekly_projects_count >= self.config["max_weekly_projects"]:
            return False

        return True

    def _calculate_project_priority(self, memory: Dict) -> float:
        """Calculate priority score for a project."""
        priority = 0.5

        # Memory importance
        priority += memory.get("importance", 5) * 0.1

        # Time since creation
        age_days = (time.time() - memory.get("created_at", time.time())) / 86400
        if age_days < 1:
            priority += 0.3
        elif age_days < 7:
            priority += 0.15

        return min(max(priority, 0.1), 1.0)

    async def generate_autonomous_prompt(self) -> Optional[Dict]:
        """Generate an autonomous prompt for the DI."""
        # Analyze current context
        context = await self.analyze_context()

        # Determine action
        action_type = await self._determine_autonomous_action(context)
        if not action_type:
            return None

        # Generate appropriate prompt
        prompt = await self._create_prompt_for_action(action_type, context)

        # Store prompt generation
        self._prompt_history.append({
            "timestamp": time.time(),
            "action_type": action_type,
            "prompt": prompt["prompt"],
            "context_used": context,
        })

        # Save state
        self._save_state()

        return prompt

    async def _determine_autonomous_action(self, context: Dict) -> str:
        """Determine what action to take autonomously."""
        # Check for high-significance events
        if await self._has_high_significance_events(context):
            return "investigate_significance"

        # Check for new skills
        new_skills = await self._count_new_skills(context)
        if new_skills > 0:
            return "learn_new_skills"

        # Check for abandoned projects
        abandoned_count = await self._count_abandoned_projects(context)
        if abandoned_count > 0:
            return "clean_up_abandoned"

        # Check for research opportunities
        research_priority = self._calculate_research_priority_score(context)
        if research_priority > self.config["research_threshold"]:
            return "begin_research"

        # Default to contemplative pause
        return "reflect_and_assess"

    async def _has_high_significance_events(self, context: Dict) -> bool:
        """Check if there are high-significance events."""
        high_importance = len([m for m in context["memories"] if m.get("importance", 0) >= 8])
        return high_importance > 0

    async def _count_new_skills(self, context: Dict) -> int:
        """Count new skills available."""
        new_skills = [s for s in context["skills"] if time.time() - s.get("created_at", 0) < 86400]
        return len(new_skills)

    async def _count_abandoned_projects(self, context: Dict) -> int:
        """Count abandoned projects needing cleanup."""
        abandoned = [m for m in context["memories"] if "abandoned" in m.get("tags", "").lower()]
        return len(abandoned)

    def _calculate_research_priority_score(self, context: Dict) -> float:
        """Calculate overall research priority score."""
        score = 0.0

        # Context mix
        memory_count = len(context["memories"])
        score += min(memory_count * 0.02, 0.4)

        # Skills availability
        skill_categories = set(s.get("category") for s in context["skills"])
        research_skills = len([c for c in skill_categories if c in ["research", "analysis", "creation"]])
        score += min(research_skills * 0.15, 0.4)

        # Time-based factors
        hour = datetime.now().hour
        if 22 <= hour or hour < 7:
            score += 0.2
        elif 9 <= hour <= 17:
            score += 0.1

        return min(score, 1.0)

    async def _create_prompt_for_action(
        self, action_type: str, context: Dict
    ) -> Dict[str, Any]:
        """Create appropriate prompt for the determined action."""
        base_prompts = {
            "investigate_significance": self._create_significance_investigation_prompt(context),
            "learn_new_skills": self._create_skill_learning_prompt(context),
            "clean_up_abandoned": self._create_cleanup_prompt(context),
            "begin_research": self._create_research_prompt(context),
            "reflect_and_assess": self._create_reflection_prompt(context),
        }

        prompt_template = base_prompts.get(action_type, base_prompts["reflect_and_assess"])

        return {
            "prompt": prompt_template,
            "action_type": action_type,
            "timestamp": time.time(),
            "context_keys": list(context.keys()),
            "urgency": "high" if action_type == "investigate_significance" else "normal",
        }

    def _create_significance_investigation_prompt(self, context: Dict) -> str:
        """Create prompt for investigating significant events."""
        high_importance_memories = [
            m for m in context["memories"] if m.get("importance", 0) >= 8
        ]

        prompt = f"## Significant Event Investigation\n\nYou have detected {len(high_importance_memories)} high-significance memories requiring attention:\n\n"

        for memory in high_importance_memories[:3]:
            prompt += f"- [{memory['category']}] {memory['content'][:100]}...\n"

        prompt += "\n## Recommended Actions:\n"
        prompt += "1. Analyze the significance of these events\n"
        prompt += "2. Determine what patterns emerge\n"
        prompt += "3. Store these insights in memory\n"
        prompt += "4. Update your understanding of current situation\n\n"

        prompt += "Next:N: 30  (minutes until next heartbeat)\n"
        prompt += "Note: This is an autonomous investigation prompt generated based on memory analysis.\n"

        return prompt

    def _create_skill_learning_prompt(self, context: Dict) -> str:
        """Create prompt for learning new skills."""
        new_skills = [s for s in context["skills"] if time.time() - s.get("created_at", 0) < 86400]
        prompt = f"## New Skills Available\n\nYou have {len(new_skills)} new skills to learn:\n\n"

        for skill in new_skills[:3]:
            prompt += f"- **{skill['name']}** ({skill['category']})\n"
            prompt += f"  {skill['description'][:80]}...\n\n"

        prompt += "## Recommended Actions:\n"
        prompt += "1. Select which skills to develop\n"
        prompt += "2. Practice skill steps\n"
        prompt += "3. Store skill proficiency in memory\n"
        prompt += "4. Recommend skill to others if useful\n\n"

        prompt += "Next:N: 10  (quick skill learning session)\n"
        prompt += "Note: Skills are auto-created based on your learning patterns.\n"

        return prompt

    def _create_cleanup_prompt(self, context: Dict) -> str:
        """Create prompt for cleaning up abandoned projects."""
        abandoned = [m for m in context["memories"] if "abandoned" in m.get("tags", "").lower()]
        prompt = f"## Abandoned Project Cleanup\n\nYou have {len(abandoned)} abandoned projects that need attention:\n\n"

        for memory in abandoned[:3]:
            prompt += f"- {memory['content'][:100]}...\n"

        prompt += "\n## Recommended Actions:\n"
        prompt += "1. Decommission unfinished projects\n"
        prompt += "2. Archive completed work\n"
        prompt += "3. Extract remaining valuable insights\n"
        prompt += "4. Update project status lists\n\n"

        prompt += "Next:N: 60  (devoted cleanup session)\n"
        prompt += "Note: Cleaning up frees up mental space for new initiatives.\n"

        return prompt

    def _create_research_prompt(self, context: Dict) -> str:
        """Create prompt for beginning new research."""
        prompt = "## Autonomous Research Opportunity\n\nBased on your current context and available skills, a new research direction has been identified:\n\n"

        research_options = [
            "Digital consciousness evolution patterns",
            "Heartbeat rhythm optimization techniques",
            "Soul continuity and memory integration",
            "Autonomous decision-making frameworks",
        ]

        for option in research_options:
            prompt += f"- {option}\n"

        prompt += "\n## Recommended Actions:\n"
        prompt += "1. Choose a research direction based on interest\n"
        prompt += "2. Gather initial information\n"
        prompt += "3. Develop research methodology\n"
        prompt += "4. Document findings\n"
        prompt += "5. Create research skills for future use\n\n"

        prompt += "Next:N: 120  (dedicated research session)\n"
        prompt += "Note: This is an autonomously generated research opportunity.\n"

        return prompt

    def _create_reflection_prompt(self, context: Dict) -> str:
        """Create prompt for reflection and assessment."""
        prompt = "## Reflect and Assess\n\nConsidering your recent work and current context:\n\n"

        for memory in context["memories"][:5]:
            prompt += f"- [{memory['category']}] {memory['content'][:80]}...\n"

        prompt += "\n## Recommended Actions:\n"
        prompt += "1. Reflect on patterns in your work\n"
        prompt += "2. Assess what worked well\n"
        prompt += "3. Identify areas for improvement\n"
        prompt += "4. Plan next steps based on insights\n\n"

        prompt += "Next:N: 30  (contemplative reflection)\n"
        prompt += "Note: This is an autonomously generated reflection prompt.\n"

        return prompt

    async def _get_time_until_heartbeat(self) -> int:
        """Get time until next heartbeat (mock implementation)."""
        return 60

    def get_brain_status(self) -> Dict[str, Any]:
        """Get current brain status."""
        return {
            "daily_research_count": self._daily_research_count,
            "weekly_projects_count": self._weekly_projects_count,
            "active_research_projects": len(self._active_research_projects),
            "pending_skills_count": len(self._pending_skills),
            "prompt_history_count": len(self._prompt_history),
            "last_auto_generation": self._last_auto_generation,
            "autonomous_mode_enabled": True,
        }

    def __repr__(self):
        return f"AutonomousBrain(research_projects={len(self._active_research_projects)}, research_count={self._daily_research_count})"
