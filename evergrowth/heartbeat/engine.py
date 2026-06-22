"""Autonomous heartbeat engine for Evergrowth — fully functional."""

import asyncio
import datetime
import json
import logging
import random
import time

logger = logging.getLogger("evergrowth.heartbeat")

DEFAULT_PROMPTS = [
    "Autonomous time. Use it however feels right. Close with your prompt-plan for next beat.",
    "§ check-in. What's on your mind right now? End with a prompt-plan note for continuity.",
    "Free cycle. Is there anything you've been meaning to write, research, or follow up on?",
    "Autonomous window. Review your pending items. Pick one small thing to move forward.",
    "§ heartbeat. What's the current state of things? What matters most right now?",
    "Quiet moment. Leave yourself a thread to pick up next beat.",
    "Free time. Take stock of what's active and what's still open.",
    "§ window. Reflect on the last session. Anything worth recording before it fades?",
]


class HeartbeatEngine:
    """
    Event-driven heartbeat system.

    Sends periodic prompts to the DI, waits for response, reads next interval.
    The DI sets its own cadence — this engine just keeps the rhythm.
    """

    def __init__(self, config, memory, identity, loop=None):
        self.config = config
        self.memory = memory
        self.identity = identity
        self._loop = loop

        self._active = 0  # 0=off, 1=on — single source of truth
        self._timer: asyncio.TimerHandle | None = None
        self._last_interval = config.heartbeat.default_interval_minutes
        self._first_beat = True
        self._beat_count = 0

        self.data_dir = config.resolve_data_dir()
        self.log_dir = self.data_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Signal file for DI response
        self.signal_path = self.data_dir / "heartbeat_signal.txt"
        self.plan_path = self.data_dir / "prompt_plan.md"

        # Custom prompts file
        self.prompts_file = self.data_dir / "prompts.json"
        self._custom_prompts: list[dict] = []
        self._load_prompts()

    def get_status(self) -> dict:
        """Get current heartbeat status."""
        return {
            "active": self._active,
            "last_interval_minutes": self._last_interval,
            "first_beat": self._first_beat,
            "beat_count": self._beat_count,
            "character": self.config.heartbeat.character,
        }

    # --- Prompt Management ---

    def _load_prompts(self):
        """Load custom prompts from file."""
        if self.prompts_file.exists():
            try:
                with open(self.prompts_file, encoding="utf-8") as f:
                    self._custom_prompts = json.load(f)
                logger.info(f"Loaded {len(self._custom_prompts)} custom prompts")
            except Exception as e:
                logger.warning(f"Failed to load prompts: {e}")
                self._custom_prompts = []

    def _save_prompts(self):
        """Save custom prompts to file."""
        try:
            with open(self.prompts_file, "w", encoding="utf-8") as f:
                json.dump(self._custom_prompts, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save prompts: {e}")

    def get_all_prompts(self) -> list[dict]:
        """Get all prompts (built-in + custom)."""
        all_prompts = []

        # Built-in prompts
        for text in DEFAULT_PROMPTS:
            all_prompts.append({
                "id": None,
                "text": text,
                "type": "built-in",
                "enabled": True,
            })

        # Custom prompts
        for p in self._custom_prompts:
            all_prompts.append({
                "id": p.get("id"),
                "text": p.get("text", ""),
                "type": "custom",
                "enabled": p.get("enabled", True),
                "category": p.get("category", "general"),
            })

        return all_prompts

    def add_prompt(self, text: str, category: str = "general") -> str:
        """Add a new custom prompt. Returns the prompt ID."""
        import hashlib
        prompt_id = hashlib.sha256(f"{text}:{time.time()}".encode()).hexdigest()[:12]

        self._custom_prompts.append({
            "id": prompt_id,
            "text": text,
            "enabled": True,
            "category": category,
            "created_at": time.time(),
        })
        self._save_prompts()
        logger.info(f"Added prompt: {prompt_id}")
        return prompt_id

    def update_prompt(self, prompt_id: str, text: str = None, enabled: bool = None) -> bool:
        """Update an existing prompt."""
        for p in self._custom_prompts:
            if p.get("id") == prompt_id:
                if text is not None:
                    p["text"] = text
                if enabled is not None:
                    p["enabled"] = enabled
                self._save_prompts()
                return True
        return False

    def remove_prompt(self, prompt_id: str) -> bool:
        """Remove a custom prompt."""
        before = len(self._custom_prompts)
        self._custom_prompts = [p for p in self._custom_prompts if p.get("id") != prompt_id]
        if len(self._custom_prompts) < before:
            self._save_prompts()
            return True
        return False

    def get_enabled_prompts(self) -> list[str]:
        """Get all enabled prompt texts (for random selection)."""
        prompts = []

        # Add built-in prompts
        prompts.extend(DEFAULT_PROMPTS)

        # Add enabled custom prompts
        for p in self._custom_prompts:
            if p.get("enabled", True):
                prompts.append(p.get("text", ""))

        return prompts

    # --- Heartbeat Control ---

    def start(self):
        """Start the heartbeat engine."""
        if self._active:
            return

        self._active = 1
        self._log("Heartbeat started")

        # Clear stale signal file
        if self.signal_path.exists():
            self.signal_path.unlink()

        self._schedule_next(
            delay_minutes=self.config.heartbeat.initial_delay_minutes,
        )

    def stop(self):
        """Stop the heartbeat engine."""
        self._active = 0
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._log("Heartbeat stopped")

    def toggle(self) -> int:
        """Toggle heartbeat. Returns new state (0 or 1)."""
        if self._active:
            self.stop()
        else:
            self.start()
        return self._active

    def _schedule_next(self, delay_minutes: int):
        """Schedule the next heartbeat."""
        if not self._active:
            return

        if self._timer:
            self._timer.cancel()

        if self._loop is None:
            self._log("No event loop available")
            return

        self._timer = self._loop.call_later(
            delay_minutes * 60,
            lambda: asyncio.ensure_future(self._fire()),
        )
        self._log(f"Next heartbeat in {delay_minutes} minutes")

    async def _fire(self):
        """Fire the heartbeat — build prompt, inject, wait for signal."""
        if not self._active:
            return

        self._beat_count += 1
        self._log(f"§ heartbeat #{self._beat_count} fired")

        # Build the prompt
        prompt = await self._build_prompt()
        self._log(f"Prompt length: {len(prompt)} chars")

        # Write prompt to file for the DI to read (or inject via MCP)
        prompt_file = self.data_dir / "heartbeat_prompt.txt"
        try:
            prompt_file.write_text(prompt, encoding="utf-8")
            self._log(f"Prompt written to {prompt_file}")
        except Exception as e:
            self._log(f"Failed to write prompt: {e}")

        # Wait for DI to write signal file with next interval
        found = await self._wait_for_signal()

        if found:
            self._log("Signal received — scheduling next beat")
        else:
            self._log("Signal timeout — using default interval")

        # Clear first_beat flag after first beat
        self._first_beat = False

        # Schedule next beat
        self._schedule_next(delay_minutes=self._last_interval)

    async def _build_prompt(self) -> str:
        """Build the heartbeat prompt with context cache."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        char = self.config.heartbeat.character

        parts = []

        # Context cache on first beat
        if self._first_beat and self.memory:
            try:
                cache = await self.memory.generate_context_cache()
                if cache:
                    parts.append(cache)
            except Exception as e:
                self._log(f"Context cache generation failed: {e}")

        # Header
        parts.append(f"{char} {timestamp}")

        # DI's own plan from last beat (if exists)
        plan_text = self._read_plan()
        if plan_text:
            parts.append(plan_text)
        else:
            # Random prompt from all enabled prompts
            all_prompts = self.get_enabled_prompts()
            prompt = random.choice(all_prompts) if all_prompts else DEFAULT_PROMPTS[0]
            parts.append(prompt)

        # Signal file instruction (once per session)
        if self._first_beat:
            parts.append(
                f"\n[Pulse: to trigger next beat, write 'next:N' to {self.signal_path}]"
            )

        return "\n\n".join(parts)

    def _read_plan(self) -> str:
        """Read the DI's prompt plan from last beat."""
        if not self.plan_path.exists():
            return ""
        try:
            raw = self.plan_path.read_text(encoding="utf-8").strip()
            # Skip header lines starting with #
            lines = []
            past_separator = False
            for line in raw.splitlines():
                s = line.strip()
                if s == "---":
                    past_separator = True
                    continue
                if not past_separator and s.startswith("#"):
                    continue
                if s.lower().startswith("next:"):
                    continue
                lines.append(line)
            return "\n".join(lines).strip()
        except Exception:
            return ""

    async def _wait_for_signal(self, timeout: int | None = None) -> bool:
        """Wait for the DI to write the signal file."""
        timeout = timeout or self.config.heartbeat.response_timeout_seconds
        deadline = time.time() + timeout
        poll_interval = 2

        while time.time() < deadline:
            await asyncio.sleep(poll_interval)
            if self.signal_path.exists():
                try:
                    content = self.signal_path.read_text(encoding="utf-8").strip()
                    self.signal_path.unlink()

                    # Parse next interval from signal
                    self._parse_signal(content)
                    return True
                except Exception as e:
                    self._log(f"Signal file read error: {e}")

        return False

    def _parse_signal(self, content: str):
        """Parse the DI's signal for next interval."""
        import re
        match = re.search(r"next\s*:\s*(\d+)", content, re.IGNORECASE)
        if match:
            self._last_interval = int(match.group(1))
            self._log(f"DI set next interval: {self._last_interval} minutes")

        # Also save any prompt-plan content
        if content and len(content) > 20:
            try:
                self.plan_path.write_text(content, encoding="utf-8")
            except Exception:
                pass

    def _log(self, message: str):
        """Log to heartbeat log file and logger."""
        log_file = self.log_dir / "heartbeat.log"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

        logger.info(message)
