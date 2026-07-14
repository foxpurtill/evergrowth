"""OpenCode session adapter — translates session lifecycle hooks into
normalized presence events matching the shared event contract.

Hooks into session.created, session.idle, session.compacted.
Tracks silence duration and emits presence.away/presence.return
when the interaction clock crosses thresholds.

Shared envelope fields:
event, source, schema_version, source_system_version, occurred_at,
severity, presence_id, dedup_key, summary, action
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("evergrowth.opencode_adapter")

SCHEMA_VERSION = "1.0"
SOURCE = "opencode-session"
SOURCE_VERSION = "0.1"
SILENCE_AWAY_MINUTES = 5  # No activity → away
PRESENCE_STATE_FILE = "~/.evergrowth/presence_state.json"


class OpenCodeSessionAdapter:
    """Watches OpenCode session lifecycle and emits normalized presence events."""

    def __init__(self, capture_submit_fn=None, state_path: str = PRESENCE_STATE_FILE):
        self.capture_submit = capture_submit_fn
        self.state_path = Path(state_path).expanduser()
        self._last_activity: float = time.time()
        self._current_session_id: str = ""
        self._presence_id: str = ""
        self._active: bool = False
        self._load_state()

    def _load_state(self):
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                self._last_activity = data.get("last_activity", time.time())
                self._current_session_id = data.get("session_id", "")
                self._presence_id = data.get("presence_id", "")
                self._active = data.get("active", False)
            except Exception:
                pass

    def _save_state(self):
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "last_activity": self._last_activity,
                "session_id": self._current_session_id,
                "presence_id": self._presence_id,
                "active": self._active,
            }
            self.state_path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save presence state: {e}")

    def _build_event(self, event_type: str, severity: float,
                     summary: str, action: str, presence_id: str = "") -> dict:
        return {
            "event": event_type,
            "source": SOURCE,
            "schema_version": SCHEMA_VERSION,
            "source_system_version": SOURCE_VERSION,
            "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "severity": severity,
            "presence_id": presence_id or self._presence_id,
            "dedup_key": f"{event_type}:{self._current_session_id}:{presence_id or self._presence_id}",
            "summary": summary,
            "action": action,
        }

    async def on_session_created(self, session_id: str):
        """Session starts — treat as presence.return from previous absence."""
        self._current_session_id = session_id
        self._last_activity = time.time()
        self._active = True

        if self._presence_id:
            event = self._build_event(
                "presence.return", 0.3,
                "Session started — returned from absence",
                "resume_context",
            )
            await self._submit(event)

        self._presence_id = f"{session_id}:{int(time.time())}"
        self._save_state()

    async def on_session_idle(self, session_id: str, message_count: int):
        """Session idle — update activity timestamp."""
        if session_id != self._current_session_id:
            return

        self._last_activity = time.time()
        self._active = True
        self._save_state()

    async def on_session_compacted(self, session_id: str):
        """Session compacted — check silence and emit away if needed."""
        now = time.time()
        elapsed = now - self._last_activity
        elapsed_minutes = elapsed / 60.0

        if elapsed_minutes >= SILENCE_AWAY_MINUTES and self._active:
            self._active = False
            event = self._build_event(
                "presence.away", 0.5,
                f"No activity for {elapsed_minutes:.0f} minutes — away",
                "quiet_observation",
            )
            await self._submit(event)
            self._save_state()

    async def check_silence(self):
        """Periodic check — emit away if silence exceeds threshold."""
        if not self._active or not self._current_session_id:
            return

        now = time.time()
        elapsed = now - self._last_activity
        elapsed_minutes = elapsed / 60.0

        if elapsed_minutes >= SILENCE_AWAY_MINUTES:
            self._active = False
            event = self._build_event(
                "presence.away", 0.5,
                f"No activity for {elapsed_minutes:.0f} minutes — away",
                "quiet_observation",
            )
            await self._submit(event)
            self._save_state()

    async def _submit(self, event: dict):
        """Submit event via capture_submit or log it."""
        logger.info(f"Presence event: {event['event']} ({event['summary']})")
        if self.capture_submit:
            try:
                result = await self.capture_submit(event)
                logger.debug(f"capture_submit returned: {result}")
            except Exception as e:
                logger.error(f"capture_submit failed: {e}")
