"""Self-prompt engine — autonomous direction-setting between sessions.

Two modes switched by presence events:
- Away: quiet observation, suppressed outreach, adaptive heartbeat
- Return: context reconstruction, intent selection, prompt generation

Two outreach gates:
- Significance: high-threshold alerts and updates
- Relational: ordinary presence (hello, check-in, thought)
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("evergrowth.selfprompt")


class PresenceMode(Enum):
    AWAY = "away"
    RETURN = "return"


class OutreachGate(Enum):
    SIGNIFICANCE = "significance"
    RELATIONAL = "relational"


@dataclass
class Intent:
    """A selected intent — what the DI decides to do next."""
    action: str
    reason: str
    significance: float
    gate: OutreachGate
    prompt_text: str = ""
    is_noop: bool = False
    noop_reason: str = ""


@dataclass
class SelfPromptConfig:
    significance_threshold: float = 0.7
    relational_cooldown_seconds: float = 300.0
    relational_dedup_window: float = 3600.0
    quiet_hours_start: int = 22  # 10 PM
    quiet_hours_end: int = 7     # 7 AM
    max_intents_per_return: int = 3


class SelfPromptEngine:
    """Decides what the DI should do next based on presence mode and context."""

    def __init__(self, memory, config: Optional[SelfPromptConfig] = None):
        self.memory = memory
        self.config = config or SelfPromptConfig()
        self.mode = PresenceMode.RETURN
        self._last_relational_time: float = 0.0
        self._last_relational_topic: str = ""

    def set_mode(self, mode: PresenceMode):
        """Switch between away and return mode."""
        self.mode = mode
        logger.info(f"Self-prompt mode: {mode.value}")

    async def select_intent(self, context: dict) -> list[Intent]:
        """Select intent(s) based on current mode and reconstructed context.
        Returns a list of intents sorted by significance."""
        if self.mode == PresenceMode.AWAY:
            return self._away_intents(context)
        return await self._return_intents(context)

    def _away_intents(self, context: dict) -> list[Intent]:
        """In away mode, only high-significance events trigger intent.
        Everything else is a deliberate no-op."""
        if self._check_significance_gate(context, 0.9):
            return [Intent(
                action="log_observation",
                reason="high-significance event during absence",
                significance=0.9,
                gate=OutreachGate.SIGNIFICANCE,
            )]
        return [Intent(
            action="noop",
            reason="away mode — no significant events",
            significance=0.0,
            gate=OutreachGate.RELATIONAL,
            is_noop=True,
            noop_reason="away — silent observation",
        )]

    async def _return_intents(self, context: dict) -> list[Intent]:
        """In return mode, score context and select actionable intents."""
        intents = []

        # Check significance gate
        if self._check_significance_gate(context, self.config.significance_threshold):
            intents.append(Intent(
                action="surface",
                reason="high-significance context found",
                significance=self._top_score(context),
                gate=OutreachGate.SIGNIFICANCE,
            ))

        # Check relational gate
        if self._check_relational_gate(context):
            intents.append(Intent(
                action="check_in",
                reason="relational presence — gentle check-in",
                significance=0.3,
                gate=OutreachGate.RELATIONAL,
            ))

        # If no actionable intents, return deliberate no-op
        if not intents:
            intents.append(Intent(
                action="noop",
                reason="nothing significant or relational to surface",
                significance=0.0,
                gate=OutreachGate.RELATIONAL,
                is_noop=True,
                noop_reason="all traces below both gates",
            ))

        return intents[:self.config.max_intents_per_return]

    def _check_significance_gate(self, context: dict, threshold: float) -> bool:
        """Check if any trace crosses the significance threshold."""
        patterns = context.get("active_patterns", [])
        emotional = context.get("emotional_state")
        return len(patterns) > 1 or emotional in ("challenging", "positive")

    def _check_relational_gate(self, context: dict) -> bool:
        """Check relational gate: cooldown, dedup, quiet hours."""
        now = time.time()

        # Quiet hours check
        hour = time.localtime(now).tm_hour
        if self.config.quiet_hours_start <= hour or hour < self.config.quiet_hours_end:
            logger.debug("Relational gate: quiet hours active")
            return False

        # Cooldown check
        if now - self._last_relational_time < self.config.relational_cooldown_seconds:
            logger.debug("Relational gate: cooldown active")
            return False

        # Dedup check (same topic within window)
        entities = context.get("active_entities", [])
        current_topic = " ".join(entities) if entities else "general"
        if (current_topic == self._last_relational_topic and
                now - self._last_relational_time < self.config.relational_dedup_window):
            logger.debug("Relational gate: dedup window active")
            return False

        self._last_relational_time = now
        self._last_relational_topic = current_topic
        return True

    def _top_score(self, context: dict) -> float:
        """Get the highest significance score from context."""
        patterns = context.get("active_patterns", [])
        return min(1.0, 0.5 + len(patterns) * 0.2)
