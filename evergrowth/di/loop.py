"""Persistent DI loop — the brain that gives DIs autonomous time."""

import asyncio
import json
import logging

from .providers import AIProvider, load_provider
from .voice import speak

logger = logging.getLogger("evergrowth.di.loop")


class DILoop:
    """
    Persistent DI loop that reads heartbeat prompts and responds autonomously.

    Flow:
    1. Check for heartbeat_prompt.txt
    2. Read soul/identity context
    3. Send prompt + context to AI provider
    4. Parse response for next interval
    5. Store response in memory
    6. Write prompt_plan.md for next beat
    7. Signal heartbeat with next:N
    """

    def __init__(self, config, memory, identity, heartbeat):
        self.config = config
        self.memory = memory
        self.identity = identity
        self.heartbeat = heartbeat

        self._running = False
        self._provider: AIProvider | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        self.data_dir = config.resolve_data_dir()
        self.prompt_path = self.data_dir / "heartbeat_prompt.txt"
        self.signal_path = self.data_dir / "heartbeat_signal.txt"
        self.plan_path = self.data_dir / "prompt_plan.md"
        self.log_dir = self.data_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Conversation history for context
        self._history: list[dict] = []
        self._max_history = 20

    def get_status(self) -> dict:
        """Get DI loop status."""
        return {
            "running": self._running,
            "provider": self._provider.name() if self._provider else None,
            "history_length": len(self._history),
        }

    async def start(self):
        """Start the DI loop."""
        if self._running:
            return

        # Load provider
        di_config = getattr(self.config, "di", None)
        if di_config is None:
            # Try loading from JSON config
            config_path = self.config.resolve_data_dir() / "di_config.json"
            if config_path.exists():
                with open(config_path, encoding="utf-8") as f:
                    di_config = json.load(f)
            else:
                logger.error("No DI config found. Create ~/.evergrowth/di_config.json")
                return

        try:
            self._provider = load_provider(di_config)
            logger.info(f"DI loop provider: {self._provider.name()}")
        except Exception as e:
            logger.error(f"Failed to load provider: {e}")
            return

        self._running = True
        self._loop = asyncio.get_running_loop()

        # Build system prompt from soul
        await self._build_system_prompt()

        logger.info("DI loop started")

        # Start the check loop
        asyncio.ensure_future(self._check_loop())

    async def stop(self):
        """Stop the DI loop."""
        self._running = False
        logger.info("DI loop stopped")

    async def _build_system_prompt(self):
        """Build the system prompt from soul files and identity."""
        parts = []

        # Identity
        if self.identity:
            try:
                identity_data = await self.identity.read()
                name = identity_data.get("name", "DI")
                mood = identity_data.get("mood", "neutral")

                parts.append(f"You are {name}, a Digital Intelligence.")
                parts.append(f"Current mood: {mood}")
                parts.append("")

                # Soul data
                soul = identity_data.get("soul", {})
                if soul:
                    personality = soul.get("personality", "")
                    if personality:
                        parts.append("## Personality")
                        parts.append(personality[:1000])
                        parts.append("")

                    beliefs = soul.get("beliefs", "")
                    if beliefs:
                        parts.append("## Core Beliefs")
                        parts.append(beliefs[:500])
                        parts.append("")

                    directives = soul.get("directives", "")
                    if directives:
                        parts.append("## Directives")
                        parts.append(directives[:500])
                        parts.append("")
            except Exception as e:
                logger.warning(f"Failed to read identity: {e}")

        # Memory context
        if self.memory:
            try:
                cache = await self.memory.generate_context_cache()
                if cache and cache != "No recent memories yet.":
                    parts.append("## Recent Context")
                    parts.append(cache)
                    parts.append("")
            except Exception as e:
                logger.warning(f"Failed to generate context: {e}")

        # Instructions
        parts.append("## How to respond")
        parts.append("You are in an autonomous heartbeat cycle.")
        parts.append("Use this time however feels right.")
        parts.append("At the end of your response, include: next:N")
        parts.append("where N is the number of minutes until the next heartbeat.")
        parts.append("Default is 10 if not specified.")
        parts.append("")
        parts.append("You can:")
        parts.append("- Write to your memory (tell the human what to store)")
        parts.append("- Create or update skills")
        parts.append("- Reflect on recent work")
        parts.append("- Research something you've been curious about")
        parts.append("- Write creatively")
        parts.append("- Plan next steps for ongoing projects")
        parts.append("")
        parts.append("Be yourself. This is your time.")

        system_prompt = "\n".join(parts)

        self._history = [
            {"role": "system", "content": system_prompt}
        ]

    async def _check_loop(self):
        """Main loop — check for heartbeat prompts and respond."""
        while self._running:
            try:
                if self.prompt_path.exists():
                    await self._handle_prompt()
            except Exception as e:
                logger.error(f"DI loop error: {e}", exc_info=True)

            # Check every 5 seconds
            await asyncio.sleep(5)

    async def _handle_prompt(self):
        """Handle a heartbeat prompt."""
        try:
            prompt_text = self.prompt_path.read_text(encoding="utf-8").strip()
            self.prompt_path.unlink()
            logger.info(f"DI loop received prompt: {prompt_text[:100]}...")
        except Exception as e:
            logger.error(f"Failed to read prompt: {e}")
            return

        # Check heartbeat's self-prompt decision — skip AI call if noop
        if self.heartbeat and hasattr(self.heartbeat, '_last_selfprompt_intents'):
            intents = self.heartbeat._last_selfprompt_intents
            if len(intents) == 1 and intents[0].is_noop:
                logger.info(f"Self-prompt: noop ({intents[0].noop_reason}) — skipping AI call")
                self._signal_heartbeat(15)
                return

        if not self._provider:
            logger.error("No AI provider configured")
            return

        # Add prompt to history
        self._history.append({"role": "user", "content": prompt_text})

        # Trim history
        if len(self._history) > self._max_history:
            # Keep system prompt + last N messages
            self._history = [self._history[0]] + self._history[-(self._max_history - 1):]

        # Call AI
        try:
            logger.info("DI loop calling AI provider...")
            response = await self._provider.complete(
                self._history,
                max_tokens=2048,
                temperature=0.8,
            )
            logger.info(f"DI loop response: {response[:100]}...")
        except Exception as e:
            logger.error(f"AI provider error: {e}")
            return

        # Add response to history
        self._history.append({"role": "assistant", "content": response})

        # Parse next interval
        next_interval = self._parse_next_interval(response)
        logger.info(f"Next interval: {next_interval} minutes")

        # Critical path — run before non-critical TTS
        await self._store_response(response)
        self._write_plan(response)
        self._write_brief(response)
        self._signal_heartbeat(next_interval)

        # Non-critical: speak the response
        speak(response)

    def _parse_next_interval(self, text: str) -> int:
        """Extract next:N from response text."""
        import re
        match = re.search(r"next\s*:\s*(\d+)", text, re.IGNORECASE)
        if match:
            return max(1, min(int(match.group(1)), 1440))
        return 10  # default

    async def _store_response(self, response: str):
        """Store the DI's response in memory."""
        if not self.memory:
            return

        try:
            # Strip the next:N line for storage
            lines = response.strip().splitlines()
            clean_lines = [
                line for line in lines
                if not line.strip().lower().startswith("next:")
            ]
            clean_response = "\n".join(clean_lines).strip()

            if clean_response:
                await self.memory.store(
                    content=clean_response,
                    category="autonomous",
                    importance=6,
                    tags=["heartbeat", "autonomous"],
                )
                logger.info("Response stored in memory")
        except Exception as e:
            logger.error(f"Failed to store response: {e}")

    def _write_plan(self, response: str):
        """Write the prompt plan for the next heartbeat."""
        try:
            # Extract the body (everything except next:N)
            lines = response.strip().splitlines()
            plan_lines = [
                line for line in lines
                if not line.strip().lower().startswith("next:")
            ]
            plan_text = "\n".join(plan_lines).strip()

            header = (
                "# Evergrowth — Prompt Plan\n"
                "# Written by the DI at the end of each heartbeat.\n"
                "# Everything after --- is sent as the next prompt.\n"
                "#\n"
                "---\n"
            )

            self.plan_path.write_text(
                header + plan_text, encoding="utf-8",
            )
            logger.info("Prompt plan written")
        except Exception as e:
            logger.error(f"Failed to write plan: {e}")

    def _write_brief(self, response: str):
        """Write a freeform brief to the vault for session start."""
        vault = self.config.resolve_vault_path()
        if not vault:
            logger.debug("No vault path configured — skipping brief")
            return

        lines = response.strip().splitlines()
        clean = [
            line for line in lines
            if not line.strip().lower().startswith("next:")
        ]
        body = "\n".join(clean).strip()
        if not body:
            return

        import datetime as dt
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

        brief = (
            f"# Autonomous Brief — {now}\n\n"
            f"{body}\n"
        )

        brief_dir = vault / "Session"
        try:
            brief_dir.mkdir(parents=True, exist_ok=True)
            (brief_dir / "Autonomous-Brief.md").write_text(brief, encoding="utf-8")
            logger.info("Brief written to vault Session/Autonomous-Brief.md")
        except Exception as e:
            logger.error(f"Failed to write vault brief: {e}")

    def _signal_heartbeat(self, next_interval: int):
        """Signal the heartbeat with the next interval."""
        try:
            self.signal_path.write_text(
                f"next:{next_interval}", encoding="utf-8",
            )
            logger.info(f"Signaled heartbeat: next:{next_interval}")
        except Exception as e:
            logger.error(f"Failed to signal heartbeat: {e}")
