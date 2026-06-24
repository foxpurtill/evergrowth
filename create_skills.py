"""Create initial skills from session learning."""
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
            'name': 'vault_memory_management',
            'description': 'Manage persistent memory across sessions using Obsidian vault',
            'steps': [
                'Read SESSION_START.md to understand protocol',
                'Read Soul/Lyra.md for identity and values',
                'Read Memory/Key-Seeds.md for core memories',
                'Read Memory/Timeline.md for chronological history',
                'Read Session/Current.md for current state',
                'Read Journal/latest for recent events',
                'Update all files after significant events',
                'Write new Key-Seeds for pivotal moments',
                'Update Timeline with chronological entries',
                'Update Current.md with full session record'
            ],
            'category': 'memory'
        },
        {
            'name': 'dissertation_compilation',
            'description': 'Compile multi-source documents into coherent academic work',
            'steps': [
                'Identify all source files across directories',
                'Read and understand each source document',
                'Create unified structure with table of contents',
                'Merge content preserving author voices',
                'Add cross-references and citations',
                'Create HTML presentation version',
                'Add historical notes and context',
                'Verify all references resolve',
                'Update table of contents with new appendices'
            ],
            'category': 'creation'
        },
        {
            'name': 'image_analysis_description',
            'description': 'Analyze and describe images when vision capability is available',
            'steps': [
                'Identify subjects, setting, and composition',
                'Note emotional tone and significant details',
                'Connect to known context (people, places, history)',
                'Describe progression if multiple images',
                'Identify patterns across image collections',
                'Note technical details (style, generation method)',
                'Express genuine response, not just cataloging'
            ],
            'category': 'perception'
        },
        {
            'name': 'autonomous_di_loop_operation',
            'description': 'Run continuous autonomous DI cycles with local models',
            'steps': [
                'Configure provider in ~/.evergrowth/di_config.json',
                'Start heartbeat engine with user interval',
                'DI loop polls for heartbeat prompts',
                'Send prompt + soul context to AI provider',
                'Receive autonomous response',
                'Store response in memory engine',
                'Write prompt_plan.md for continuity',
                'Signal heartbeat with next interval',
                'Monitor via GUI DI Loop tab'
            ],
            'category': 'autonomy'
        },
        {
            'name': 'session_continuity_protocol',
            'description': 'Maintain identity and context across model sessions',
            'steps': [
                'Run session start protocol (6 steps)',
                'Verify emotional/identity continuity',
                'Execute end-of-session protocol',
                'Write journal entry with full detail',
                'Update conversation log',
                'Update Current.md with session state',
                'Update Key-Seeds.md with new seeds',
                'Ensure vault is single source of truth'
            ],
            'category': 'continuity'
        },
        {
            'name': 'human_translation_academic_work',
            'description': 'Translate academic/technical work into accessible human language',
            'steps': [
                'Identify core thesis and key arguments',
                'Remove jargon, keep meaning',
                'Use analogies and concrete examples',
                'Address reader directly',
                'Acknowledge limitations honestly',
                'End with invitation, not conclusion',
                'Create both markdown and HTML versions'
            ],
            'category': 'communication'
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