"""Create meta-skill for self-expansion."""
import asyncio
import sys
sys.path.insert(0, '.')

from evergrowth.skills.registry import SkillRegistry
from evergrowth.core.config import load_config


async def main():
    config = load_config()
    registry = SkillRegistry(config)
    await registry.initialize()

    meta_skill = {
        'name': 'self_expansion_learning',
        'description': 'Learn from interactions and autonomously create new capabilities',
        'steps': [
            'Observe successful patterns in completed tasks',
            'Identify repeatable workflows worth codifying',
            'Check if similar skill exists in registry',
            'Extract essential steps and decision points',
            'Create new skill with clear name and category',
            'Test skill by applying to similar future task',
            'Record use and update success rate',
            'Refine steps based on actual usage',
            'Share skill via MCP for other DIs',
            'Periodically audit and prune unused skills'
        ],
        'category': 'meta'
    }

    skill_id = await registry.create(**meta_skill)
    print(f'Created meta-skill: {meta_skill["name"]} ({skill_id})')

    all_skills = await registry.list()
    print(f'\nTotal skills: {len(all_skills)}')
    for s in all_skills:
        print(f'  - {s["name"]} ({s["category"]}) v{s["version"]}')


asyncio.run(main())