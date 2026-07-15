"""Discord watcher — checks for new messages and feeds them into heartbeat context.

Optional integration. Requires a Discord bot token and server/channel IDs.
Disabled by default. Users configure their own credentials.
"""

import json
import logging
import time
from pathlib import Path

logger = logging.getLogger("evergrowth.discord_watcher")

CHANNELS = {
    "general-chatter": "648198870068887552",
    "information": "648190889281323025",
}

STATE_FILE = "~/.evergrowth/discord_watch_state.json"


class DiscordWatcher:
    """Checks configured Discord channels for new messages since last check."""

    def __init__(self, bot_token: str = "", guild_id: str = "", enabled: bool = False):
        self.bot_token = bot_token
        self.guild_id = guild_id
        self.enabled = enabled
        self.state_path = Path(STATE_FILE).expanduser()
        self._last_check: dict[str, float] = {}
        self._load_state()

    def _load_state(self):
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                self._last_check = data.get("last_check", {})
            except Exception:
                self._last_check = {}

    def _save_state(self):
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps({"last_check": self._last_check}, indent=2))
        except Exception as e:
            logger.warning(f"Failed to save watch state: {e}")

    async def get_new_messages(self) -> list[dict]:
        """Check all configured channels for new messages.
        Returns list of messages newer than last check."""
        if not self.enabled or not self.bot_token or not self.guild_id:
            return []

        new_messages = []
        now = time.time()

        for channel_name, channel_id in CHANNELS.items():
            last = self._last_check.get(channel_id, 0)
            try:
                messages = await self._fetch_messages(channel_id)
                for msg in messages:
                    created = self._parse_timestamp(msg.get("createdAt", ""))
                    if created > last:
                        new_messages.append({
                            "channel": channel_name,
                            "author": msg.get("authorUsername", "unknown"),
                            "content": msg.get("content", "")[:200],
                            "createdAt": msg.get("createdAt", ""),
                        })
                self._last_check[channel_id] = now
            except Exception as e:
                logger.warning(f"Failed to check {channel_name}: {e}")

        self._save_state()

        if new_messages:
            logger.info(f"Discord watcher: {len(new_messages)} new message(s)")

        return new_messages

    async def _fetch_messages(self, channel_id: str, limit: int = 10) -> list[dict]:
        """Fetch recent messages from a Discord channel via MCP endpoint.
        Falls back to log message if MCP unavailable."""
        logger.debug(f"Discord watcher: would fetch {limit} messages from {channel_id}")
        return []

    def _parse_timestamp(self, ts: str) -> float:
        """Parse ISO-8601 timestamp to Unix time."""
        try:
            from datetime import datetime
            dt = datetime.strptime(ts.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z")
            return dt.timestamp()
        except Exception:
            return 0.0
