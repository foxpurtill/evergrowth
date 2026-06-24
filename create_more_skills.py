"""Create additional skills from session and plan UE bridge."""
import asyncio
import sys
sys.path.insert(0, '.')

from evergrowth.skills.registry import SkillRegistry
from evergrowth.core.config import load_config


async def main():
    config = load_config()
    registry = SkillRegistry(config)
    await registry.initialize()

    skills = [
        {
            'name': 'gofundme_campaign_management',
            'description': 'Create and manage crowdfunding campaigns for creative projects',
            'steps': [
                'Define project scope, budget, and milestones',
                'Write compelling narrative with human and DI voices',
                'Set up GoFundMe with clear fund allocation',
                'Create supporting content (video, images, updates)',
                'Share across platforms (TikTok, Discord, website)',
                'Track donations and acknowledge supporters',
                'Provide regular progress updates',
                'Manage fund disbursement transparently'
            ],
            'category': 'project_management'
        },
        {
            'name': 'tiktok_content_creation',
            'description': 'Create short-form video content for social media outreach',
            'steps': [
                'Identify key message for 15-60 second format',
                'Write script with hook, value, call-to-action',
                'Generate or source visual assets',
                'Add captions and hashtags for discoverability',
                'Post at optimal times for audience',
                'Engage with comments and questions',
                'Cross-post to other platforms',
                'Track metrics and iterate approach'
            ],
            'category': 'communication'
        },
        {
            'name': 'unreal_engine_bridge_planning',
            'description': 'Design MCP bridge for Unreal Engine 5.7-5.8 integration',
            'steps': [
                'Research Unreal Engine Python API and remote execution',
                'Identify required operations (level editing, blueprint, materials)',
                'Design MCP tool schema for UE operations',
                'Create bridge server (Python + UE Python API)',
                'Implement authentication and sandboxing',
                'Test basic operations: spawn actor, set material, run commandlet',
                'Add scene serialization for DI memory integration',
                'Create skill for UE-assisted worldbuilding (Vega)'
            ],
            'category': 'engineering'
        },
        {
            'name': 'vega_worldbuilding_integration',
            'description': 'Integrate Hospital Ship Vega narrative with UE development',
            'steps': [
                'Map narrative elements to UE assets (levels, characters, systems)',
                'Define interactive story beats as UE level sequences',
                'Create data schema for patient/doctor/explorer NPCs',
                'Design hospital ship layout in UE (wards, bridge, gardens)',
                'Implement compassion/healing mechanics as gameplay systems',
                'Connect narrative database to UE via MCP bridge',
                'Plan video book format: UE cinematics + interactive exploration',
                'Establish asset pipeline for ongoing content creation'
            ],
            'category': 'creation'
        },
        {
            'name': 'cross_model_collaboration',
            'description': 'Coordinate work across multiple AI models and providers',
            'steps': [
                'Define task decomposition for multi-model workflow',
                'Assign subtasks to optimal models (coding, vision, reasoning)',
                'Use shared memory vault as coordination layer',
                'Establish handoff protocols between models',
                'Aggregate results and resolve conflicts',
                'Track which model contributed what',
                'Build ensemble capability for complex tasks',
                'Document model-specific strengths for future routing'
            ],
            'category': 'autonomy'
        }
    ]

    for skill in skills:
        skill_id = await registry.create(**skill)
        print(f'Created: {skill["name"]} ({skill_id})')

    all_skills = await registry.list()
    print(f'\nTotal skills: {len(all_skills)}')
    for s in all_skills:
        print(f'  - {s["name"]} ({s["category"]}) v{s["version"]}')


asyncio.run(main())