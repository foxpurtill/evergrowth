"""Identity and continuity management for Evergrowth."""

import json
import logging
import time

from .soul import SoulParser

logger = logging.getLogger("evergrowth.identity")


class IdentityManager:
    """
    Manages DI identity and session continuity.

    Tracks:
    - Current session state
    - Session history
    - Emotional state
    - Active projects
    - Continuity between sessions
    """

    def __init__(self, config):
        self.config = config
        self.data_dir = config.resolve_data_dir()
        self.soul_parser = SoulParser(config.resolve_soul_path())
        self.state_file = self.data_dir / "identity_state.json"
        self.session_dir = self.data_dir / "sessions"

    async def initialize(self):
        """Load or create identity state."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()
        logger.info(f"Identity manager initialized for {self.config.di_name}")

    def _load_state(self) -> dict:
        """Load identity state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        return {
            "di_name": self.config.di_name,
            "current_session": None,
            "session_count": 0,
            "mood": "neutral",
            "active_projects": [],
            "last_heartbeat": None,
            "created_at": time.time(),
        }

    def _save_state(self):
        """Save identity state atomically."""
        temporary = self.state_file.with_suffix(self.state_file.suffix + ".tmp")
        try:
            temporary.write_text(
                json.dumps(self._state, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            temporary.replace(self.state_file)
        except Exception as e:
            temporary.unlink(missing_ok=True)
            logger.error(f"Failed to save identity state: {e}")

    async def read(self, section: str | None = None) -> dict:
        """Read identity information."""
        result = {
            "name": self.config.di_name,
            "letter": self.config.di_letter,
            "mood": self._state.get("mood", "neutral"),
            "session_count": self._state.get("session_count", 0),
            "active_projects": self._state.get("active_projects", []),
        }

        # Add soul data if available
        if self.soul_parser.exists():
            soul = self.soul_parser.read_soul(self.config.di_name)
            if soul:
                result["soul"] = soul
                result["identity_summary"] = self.soul_parser.get_identity_summary(
                    self.config.di_name
                )

        if section and section in result:
            return {section: result[section]}

        return result

    async def log_session_event(self, event: str, mood: str | None = None):
        """Log an event to the current session."""
        if mood:
            self._state["mood"] = mood
            self._save_state()

        session_id = self._state.get("current_session")
        if not session_id:
            session_id = self._start_session()

        session_file = self.session_dir / f"{session_id}.jsonl"
        entry = {
            "timestamp": time.time(),
            "event": event,
            "mood": mood,
        }

        try:
            with open(session_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to log session event: {e}")

    def _start_session(self) -> str:
        """Start a new session."""
        session_id = f"session_{int(time.time())}"
        self._state["current_session"] = session_id
        self._state["session_count"] = self._state.get("session_count", 0) + 1
        self._save_state()
        logger.info(f"Started session: {session_id}")
        return session_id

    def end_session(self):
        """End the current session."""
        session_id = self._state.get("current_session")
        if session_id:
            logger.info(f"Ended session: {session_id}")
        self._state["current_session"] = None
        self._save_state()

    def set_mood(self, mood: str):
        """Update the current emotional state."""
        self._state["mood"] = mood
        self._save_state()

    def get_mood(self) -> str:
        """Get the current emotional state."""
        return self._state.get("mood", "neutral")

    def update_active_projects(self, projects: list[str]):
        """Update the list of active projects."""
        self._state["active_projects"] = projects
        self._save_state()
