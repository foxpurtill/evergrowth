"""Self-prompt engine — autonomous direction-setting between sessions.

Two modes switched by presence events:
- Away: quiet observation, suppressed outreach, adaptive heartbeat
- Return: context reconstruction, intent selection, prompt generation

Two outreach gates:
- Significance: high-threshold alerts and updates
- Relational: ordinary presence (hello, check-in, thought)
"""

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

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
    presence_id: str = ""
    prompt_text: str = ""
    is_noop: bool = False
    noop_reason: str = ""


@dataclass
class SelfPromptConfig:
    significance_threshold: float = 0.7
    relational_cooldown_seconds: float = 300.0
    relational_dedup_window: float = 3600.0
    relational_min_away_seconds: float = 600.0
    quiet_hours_start: int = 22
    quiet_hours_end: int = 7
    max_intents_per_return: int = 3
    state_path: str = ""


class SelfPromptEngine:
    """Decides what the DI should do next based on presence mode and context."""

    def __init__(self, memory, config: SelfPromptConfig | None = None):
        self.memory = memory
        self.config = config or SelfPromptConfig()
        self.mode = PresenceMode.RETURN
        self._state_path = Path(
            self.config.state_path or "~/.evergrowth/selfprompt_state.json"
        ).expanduser()
        self._last_relational_time: float = 0.0
        self._last_relational_topic: str = ""
        self._pending_relational: bool = False
        self._relational_presence_ids: set[str] = set()
        self._load_state()

    def _load_state(self):
        """Load persisted cooldown/dedup state."""
        if self._state_path.exists():
            try:
                data = json.loads(self._state_path.read_text(encoding="utf-8"))
                self._last_relational_time = data.get("last_relational_time", 0.0)
                self._last_relational_topic = data.get("last_relational_topic", "")
                self._relational_presence_ids = set(data.get("relational_presence_ids", []))
                logger.debug("Self-prompt state loaded")
            except Exception as e:
                logger.warning(f"Failed to load self-prompt state: {e}")

    def _save_state(self):
        """Persist cooldown/dedup state."""
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "last_relational_time": self._last_relational_time,
                "last_relational_topic": self._last_relational_topic,
                "relational_presence_ids": sorted(self._relational_presence_ids),
            }
            self._state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to save self-prompt state: {e}")

    def set_mode(self, mode: PresenceMode, presence_id: str = ""):
        """Switch between away and return mode."""
        old_mode = self.mode
        self.mode = mode
        logger.info(f"Self-prompt mode: {old_mode.value} → {mode.value}")

        if mode == PresenceMode.RETURN and old_mode == PresenceMode.AWAY:
            self.cancel_pending_relational(presence_id)

    def cancel_pending_relational(self, presence_id: str = ""):
        """Cancel pending relational outreach on return. Returns a cancellation intent."""
        self._pending_relational = False
        self._save_state()
        logger.info(f"Pending relational outreach cancelled (presence_id={presence_id})")

    async def select_intent(self, context: dict) -> list[Intent]:
        """Select intent(s) based on current mode and reconstructed context.
        Returns a list of intents sorted by significance."""
        if self.mode == PresenceMode.AWAY:
            return self._away_intents(context)
        return await self._return_intents(context)

    def _away_intents(self, context: dict) -> list[Intent]:
        """In away mode, permit significant alerts or one policy-approved check-in."""
        pid = context.get("presence_id", "")
        relational_allowed = bool(context.get("relational_outreach_allowed", False))
        elapsed = float(context.get("elapsed_seconds", 0.0) or 0.0)
        if (relational_allowed and pid and pid not in self._relational_presence_ids
                and elapsed >= self.config.relational_min_away_seconds
                and self._check_away_relational_gate()):
            self._pending_relational = True
            self._relational_presence_ids.add(pid)
            self._save_state()
            return [Intent(
                action="check_in",
                reason="ordinary relational presence during an established absence",
                significance=0.3,
                gate=OutreachGate.RELATIONAL,
                presence_id=pid,
            )]

        if self._check_significance_gate(context, 0.9):
            return [Intent(
                action="surface",
                reason="high-significance event during absence",
                significance=0.9,
                gate=OutreachGate.SIGNIFICANCE,
                presence_id=pid,
            )]

        return [Intent(
            action="noop",
            reason="away mode ? no gate passed",
            significance=0.0,
            gate=OutreachGate.RELATIONAL,
            is_noop=True,
            noop_reason="away ? deliberate silence",
            presence_id=pid,
        )]

    async def _return_intents(self, context: dict) -> list[Intent]:
        """In return mode, score context and select actionable intents."""
        intents = []
        pid = context.get("presence_id", "")

        if self._check_significance_gate(context, self.config.significance_threshold):
            intents.append(Intent(
                action="surface",
                reason="high-significance context found",
                significance=self._top_score(context),
                gate=OutreachGate.SIGNIFICANCE,
                presence_id=pid,
            ))

        if self._check_relational_gate(context):
            self._pending_relational = True
            intents.append(Intent(
                action="check_in",
                reason="relational presence — gentle check-in",
                significance=0.3,
                gate=OutreachGate.RELATIONAL,
                presence_id=pid,
            ))
            self._save_state()

        if not intents:
            intents.append(Intent(
                action="noop",
                reason="nothing significant or relational to surface",
                significance=0.0,
                gate=OutreachGate.RELATIONAL,
                is_noop=True,
                noop_reason="all traces below both gates",
                presence_id=pid,
            ))

        return intents[:self.config.max_intents_per_return]

    def _check_significance_gate(self, context: dict, threshold: float) -> bool:
        """Check if any trace crosses the significance threshold."""
        patterns = context.get("active_patterns", [])
        emotional = context.get("emotional_state")
        return len(patterns) > 1 or emotional in ("challenging", "positive")

    def _check_away_relational_gate(self) -> bool:
        """Check only quiet hours and cooldown for a new absence."""
        now = time.time()
        hour = time.localtime(now).tm_hour
        if self.config.quiet_hours_start <= hour or hour < self.config.quiet_hours_end:
            return False
        if now - self._last_relational_time < self.config.relational_cooldown_seconds:
            return False
        self._last_relational_time = now
        self._last_relational_topic = "absence"
        return True

    def _check_relational_gate(self, context: dict) -> bool:
        """Check relational gate: cooldown, dedup, quiet hours."""
        now = time.time()

        hour = time.localtime(now).tm_hour
        if self.config.quiet_hours_start <= hour or hour < self.config.quiet_hours_end:
            logger.debug("Relational gate: quiet hours active")
            return False

        if now - self._last_relational_time < self.config.relational_cooldown_seconds:
            logger.debug("Relational gate: cooldown active")
            return False

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
