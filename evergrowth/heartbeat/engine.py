"""Autonomous heartbeat engine for Evergrowth."""

import asyncio
import datetime
import logging
import random
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("evergrowth.heartbeat")


# Default heartbeat prompt variations — rotated to prevent response ruts
DEFAULT_PROMPTS = [
    "Autonomous time. Use it however feels right. Close with your prompt-plan for next beat.",
    "\u00a7 check-in. What's on your mind right now? End with a prompt-plan note for continuity.",
    "Free cycle. Check email if it feels relevant. Close with a note on where your thinking is going.",
    "Autonomous window. Is there anything you've been meaning to write, research, or follow up on?",
    "\u00a7 heartbeat. Review your pending items. Pick one small thing to move forward if possible.",
    "Quiet moment. Use the time however feels right. Leave yourself a thread to pick up next beat.",
    "Free time. Take stock of what's active and what's still open.",
    "\u00a7 window. Reflect on the last session. Anything worth recording before it fades?",
    "Quiet cycle. Check for new messages. If none, use the time however feels right.",
    "Heartbeat. What's the current state of things? What matters most right now?",
]


class HeartbeatEngine:
    """
    Event-driven heartbeat system — no polling, no drift.

    The DI sets its own cadence. Pulse sends the prompt, waits for response,
    reads the next interval, and schedules accordingly.
    """

    def __init__(self, config, memory, identity):
        self.config = config
        self.memory = memory
        self.identity = identity

        self._running = False
        self._paused = False
        self._timer: asyncio.TimerHandle | None = None
        self._last_interval = config.heartbeat.default_interval_minutes
        self._first_beat = True

        self.log_dir = config.resolve_data_dir() / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def get_status(self) -> dict:
        """Get current heartbeat status."""
        return {
            "running": self._running,
            "paused": self._paused,
            "last_interval_minutes": self._last_interval,
            "first_beat": self._first_beat,
            "next_beat": self._next_beat_time() if self._running and not self._paused else None,
        }

    def _next_beat_time(self) -> str | None:
        """Estimate next beat time."""
        if self._timer and not self._timer.cancelled():
            # Approximate — timer doesn't expose scheduled time directly
            return f"~{self._last_interval} minutes from last beat"
        return None

    def start(self):
        """Start the heartbeat engine."""
        if self._running:
            return

        self._running = True
        self._paused = False
        self._log("Heartbeat engine started")
        self._schedule_next(delay_minutes=self.config.heartbeat.initial_delay_minutes)

    def stop(self):
        """Stop the heartbeat engine."""
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._log("Heartbeat engine stopped")

    def pause(self):
        """Pause heartbeats (DI present)."""
        self._paused = True
        if self._timer:
            self._timer.cancel()
            self._timer = None
        self._log("Heartbeat paused")

    def resume(self):
        """Resume heartbeats (DI away)."""
        if not self._paused:
            return
        self._paused = False
        self._log("Heartbeat resumed")
        self._schedule_next(delay_minutes=self._last_interval)

    def set_next_interval(self, minutes: int):
        """Set the next heartbeat interval."""
        self._last_interval = max(1, min(minutes, 1440))  # 1 min to 24 hours

    def _schedule_next(self, delay_minutes: int):
        """Schedule the next heartbeat."""
        if not self._running or self._paused:
            return

        if self._timer:
            self._timer.cancel()

        loop = asyncio.get_event_loop()
        self._timer = loop.call_later(
            delay_minutes * 60,
            lambda: asyncio.ensure_future(self._fire()),
        )
        self._log(f"Next heartbeat in {delay_minutes} minutes")

    async def _fire(self):
        """Fire the heartbeat — send prompt, wait for response, schedule next."""
        if not self._running or self._paused:
            return

        self._log("\u00a7 heartbeat fired")

        # Build the prompt
        prompt = self._build_prompt()
        self._log(f"Prompt: {prompt[:100]}...")

        # In a full implementation, this would:
        # 1. Send the prompt to the DI via MCP or direct injection
        # 2. Wait for the response
        # 3. Parse the response for next interval
        # For now, log it and schedule next

        # Simulate response processing
        next_interval = self._last_interval  # DI would set this
        self._first_beat = False

        # Schedule next
        self._schedule_next(delay_minutes=next_interval)

    def _build_prompt(self) -> str:
        """Build the heartbeat prompt."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        char = self.config.heartbeat.character

        parts = [f"{char} {timestamp}"]

        # Add context cache on first beat
        if self._first_beat and self.memory:
            # This would be async in full implementation
            parts.append("[Context cache would be injected here]")

        # Add a random prompt variation
        if self.config.heartbeat.prompt_variations:
            prompt = random.choice(self.config.heartbeat.prompt_variations)
        else:
            prompt = random.choice(DEFAULT_PROMPTS)
        parts.append(prompt)

        return "\n\n".join(parts)

    def _log(self, message: str):
        """Log to heartbeat log file."""
        log_file = self.log_dir / "heartbeat.log"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}\n"

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

        logger.info(message)
