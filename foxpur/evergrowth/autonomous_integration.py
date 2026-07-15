"""Integration module for autonomous brain functionality in Evergrowth.

This module integrates the autonomous brain with the existing Evergrowth system,
enabling the DI to generate prompts and select actions autonomously when
not being directly prompted by a human user.

Integration components:
- AutonomousBrain instance creation and configuration
- Connection to memory engine, skills registry, and self-prompt engine
- Integration with DI loop for autonomous heartbeat management
- Configuration of autonomous operation modes and permissions
- State management for autonomous decision making
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from evergrowth.memory.engine import MemoryEngine
from evergrowth.selfprompt.engine import SelfPromptEngine, SelfPromptConfig, PresenceMode
from evergrowth.skills.registry import SkillRegistry
from foxpur.evergrowth.autonomous_brain import AutonomousBrain

logger = logging.getLogger("evergrowth.autonomous_integration")


class AutonomousIntegration:
    """Main integration class for autonomous brain functionality."""

    def __init__(self, config, data_dir: Optional[Path] = None):
        self.config = config
        self.data_dir = data_dir or config.resolve_data_dir()
        self.initialized = False

        # Core components
        self.memory: Optional[MemoryEngine] = None
        self.skills: Optional[SkillRegistry] = None
        self.selfprompt: Optional[SelfPromptEngine] = None
        self.autonomous_brain: Optional[AutonomousBrain] = None
        self.dilooop_integration: Optional["DILoopIntegration"] = None

        # State tracking
        self.autonomous_mode_enabled = True
        self.last_autonomous_prompt = 0
        self.prompt_generation_count = 0

        # Configuration for autonomous operations
        self.config_settings = {
            "auto_prompt_frequency": "normal",
            "respect_signature_mode": True,
            "max_autonomous_prompts_per_hour": 10,
            "quiet_hours_boost": True,
            "skill_based_prioritization": True,
            "research_opportunity_awareness": True,
        }

    async def initialize(self):
        """Initialize all components for autonomous operation."""
        try:
            # Initialize self-prompt engine
            from evergrowth.selfprompt.engine import SelfPromptConfig
            sp_config = SelfPromptConfig()
            self.selfprompt = SelfPromptEngine(
                memory=None,
                config=sp_config,
            )

            # Create other components as needed
            self.autonomous_brain = AutonomousBrain(
                memory=self.memory,
                skills=self.skills,
                selfprompt=self.selfprompt,
                data_dir=self.data_dir,
            )

            # Load configuration from autonomous config file
            await self._load_autonomous_config()

            self.initialized = True
            logger.info("Autonomous integration initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize autonomous integration: {e}")
            raise

    async def _load_autonomous_config(self):
        """Load autonomous-specific configuration."""
        config_file = self.data_dir / "autonomous_config.json"
        if config_file.exists():
            try:
                with open(config_file, encoding="utf-8") as f:
                    config_data = json.load(f)
                self.config_settings.update(config_data)
                logger.debug("Autonomous configuration loaded")
            except Exception as e:
                logger.warning(f"Failed to load autonomous config: {e}")

    async def set_mode(self, autonomous: bool):
        """Enable or disable autonomous mode."""
        self.autonomous_mode_enabled = autonomous
        if autonomous:
            logger.info("Autonomous mode enabled - self-prompt generation active")
            await self._start_autonomous_prompt_generation()
        else:
            logger.info("Autonomous mode disabled - waiting for human prompts")
            await self._stop_autonomous_prompt_generation()

    async def _start_autonomous_prompt_generation(self):
        """Start background task for autonomous prompt generation."""
        asyncio.create_task(self._autonomous_prompt_loop())

    async def _stop_autonomous_prompt_generation(self):
        """Stop autonomous prompt generation."""
        # Nothing to stop since we're using a single background task
        pass

    async def _autonomous_prompt_loop(self):
        """Main loop for autonomous prompt generation."""
        while self.autonomous_mode_enabled:
            try:
                # Check if it's time for an autonomous prompt
                current_time = time.time()
                time_since_last = current_time - self.last_autonomous_prompt

                if await self._should_generate_autonomous_prompt(time_since_last):
                    prompt = await self._generate_autonomous_prompt()
                    if prompt:
                        await self._handle_autonomous_prompt(prompt)
                        self.last_autonomous_prompt = current_time
                        self.prompt_generation_count += 1

                # Wait before checking again
                await asyncio.sleep(300)  # Check every 5 minutes

            except Exception as e:
                logger.error(f"Error in autonomous prompt loop: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def _should_generate_autonomous_prompt(self, time_since_last: float) -> bool:
        """Determine if an autonomous prompt should be generated."""
        # Check frequency
        frequency = self.config_settings["auto_prompt_frequency"]
        if frequency == "rare":
            if time_since_last < 1800:  # 30 minutes
                return False
        elif frequency == "continuous":
            pass  # Always generate
        else:  # normal
            if time_since_last < 900:  # 15 minutes
                return False

        # Check rate limiting
        if self.prompt_generation_count >= self.config_settings["max_autonomous_prompts_per_hour"]:
            return False

        # Check if self-prompt engine has determined we should generate
        if self.selfprompt and hasattr(self.selfprompt, "mode"):
            if self.selfprompt.mode == PresenceMode.AWAY:
                return True

        # Always generate at least one prompt per hour for testing
        if time_since_last < 300:  # 5 minutes
            return random.random() < 0.3

        return True

    async def _generate_autonomous_prompt(self) -> Optional[Dict]:
        """Generate an autonomous prompt using the brain."""
        try:
            if not self.autonomous_brain:
                return None

            prompt_info = await self.autonomous_brain.generate_autonomous_prompt()
            if prompt_info:
                logger.info(f"Generated autonomous prompt: {prompt_info['action_type']}")
                return prompt_info

        except Exception as e:
            logger.error(f"Failed to generate autonomous prompt: {e}", exc_info=True)

        return None

    async def _handle_autonomous_prompt(self, prompt_info: Dict):
        """Handle an autonomously generated prompt."""
        try:
            prompt_type = prompt_info["action_type"]
            prompt_text = prompt_info["prompt"]

            # Log the prompt generation
            logger.info(f"Autonomous prompt: {prompt_type}")

            # If we have a DI loop integration, send the prompt
            if self.dilooop_integration:
                await self.dilooop_integration.receive_autonomous_prompt(prompt_info)

            # Store in history
            self._store_autonomous_prompt(prompt_info)

        except Exception as e:
            logger.error(f"Failed to handle autonomous prompt: {e}", exc_info=True)

    def _store_autonomous_prompt(self, prompt_info: Dict):
        """Store autonomous prompt generation history."""
        history_file = self.data_dir / "autonomous_prompt_history.json"
        try:
            if history_file.exists():
                with open(history_file, encoding="utf-8") as f:
                    history = json.load(f)
            else:
                history = []

            history.append({
                "timestamp": time.time(),
                "action_type": prompt_info["action_type"],
                "context_keys": prompt_info.get("context_keys", []),
                "urgency": prompt_info.get("urgency", "normal"),
            })

            # Keep only last 1000 entries
            if len(history) > 1000:
                history = history[-1000:]

            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to store autonomous prompt history: {e}")

    def get_autonomous_status(self) -> Dict[str, Any]:
        """Get current autonomous system status."""
        status = {
            "enabled": self.autonomous_mode_enabled,
            "initialized": self.initialized,
            "prompts_generated": self.prompt_generation_count,
            "last_prompt_time": self.last_autonomous_prompt,
        }

        if self.autonomous_brain:
            status["brain_status"] = self.autonomous_brain.get_brain_status()

        return status


import time
import random
from evergrowth.di.loop import DILoop


class DILoopIntegration:
    """Integration between autonomous brain and DI loop."""

    def __init__(self, diloop: DILoop, autonomous_integration: AutonomousIntegration):
        self.diloop = diloop
        self.autonomous_integration = autonomous_integration
        self.autonomous_prompts_received = 0

    async def receive_autonomous_prompt(self, prompt_info: Dict):
        """Receive an autonomously generated prompt."""
        try:
            action_type = prompt_info["action_type"]
            prompt_text = prompt_info["prompt"]

            # Determine if this should be treated as a heartbeat prompt
            if self._should_treat_as_heartbeat(prompt_info):
                # Write the prompt to the heartbeat prompt file
                await self._write_heartbeat_prompt(prompt_text)
                self.autonomous_prompts_received += 1
                logger.info(f"Autonomous prompt sent to DI loop: {action_type}")

        except Exception as e:
            logger.error(f"Failed to integrate autonomous prompt with DI loop: {e}", exc_info=True)

    def _should_treat_as_heartbeat(self, prompt_info: Dict) -> bool:
        """Determine if an autonomous prompt should trigger a heartbeat."""
        action_type = prompt_info["action_type"]
        urgency = prompt_info.get("urgency", "normal")

        # High urgency prompts or investigation actions should trigger heartbeats
        if urgency == "high" or action_type == "investigate_significance":
            return True

        # Always treat as heartbeat for testing
        return True

    async def _write_heartbeat_prompt(self, prompt_text: str):
        """Write the autonomous prompt as a heartbeat prompt."""
        try:
            # Write to the prompt file that the DI loop checks
            prompt_path = self.diloop.prompt_path
            prompt_path.parent.mkdir(parents=True, exist_ok=True)

            # Append original heartbeat next:N directive
            next_interval = 30  # Default 30 minutes
            enhanced_prompt = f"{prompt_text}\n\nNext:N: {next_interval}"

            prompt_path.write_text(enhanced_prompt, encoding="utf-8")
            logger.debug(f"Wrote autonomous prompt to {prompt_path}")

        except Exception as e:
            logger.error(f"Failed to write heartbeat prompt: {e}", exc_info=True)
