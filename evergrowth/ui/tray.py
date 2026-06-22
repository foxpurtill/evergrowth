"""System tray application for Evergrowth."""

import asyncio
import logging
import threading

import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger("evergrowth.ui.tray")


def create_icon_image(color: str = "#FF4444", letter: str = "E") -> Image.Image:
    """Create a simple tray icon with a colored circle and letter."""
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw circle
    r = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    draw.ellipse([4, 4, size - 4, size - 4], fill=r)

    # Draw letter
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), letter, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2, (size - th) / 2 - 2),
        letter, fill="white", font=font,
    )

    return img


class TrayApp:
    """
    System tray application for Evergrowth.

    Provides quick access to:
    - Heartbeat status and toggle
    - Memory and skill counts
    - DI mood and session info
    """

    def __init__(self, runtime):
        self.runtime = runtime
        self._icon = None
        self._running = False
        self._last_hb_state = None

    def start(self):
        """Start the tray app in a background thread."""
        self._running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        logger.info("Tray app started")

    def stop(self):
        """Stop the tray app."""
        self._running = False
        if self._icon:
            self._icon.stop()
        logger.info("Tray app stopped")

    def _run(self):
        """Run the tray icon (blocking call in thread)."""
        # Start red since heartbeat isn't running yet
        icon_image = create_icon_image(
            color="#FF4444",
            letter=self.runtime.config.di_letter,
        )

        menu = pystray.Menu(
            pystray.MenuItem(
                "Evergrowth",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Status",
                self._on_status,
                default=True,
            ),
            pystray.MenuItem(
                "Toggle Heartbeat",
                self._on_toggle_heartbeat,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Memory",
                pystray.Menu(
                    pystray.MenuItem("Count", self._on_memory_count),
                    pystray.MenuItem("Recent", self._on_memory_recent),
                ),
            ),
            pystray.MenuItem(
                "Skills",
                pystray.Menu(
                    pystray.MenuItem("Count", self._on_skills_count),
                    pystray.MenuItem("List", self._on_skills_list),
                ),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Quit",
                self._on_quit,
            ),
        )

        self._icon = pystray.Icon(
            "evergrowth",
            icon_image,
            "Evergrowth",
            menu,
        )

        # Start background sync thread
        sync_thread = threading.Thread(
            target=self._sync_loop, daemon=True,
        )
        sync_thread.start()

        self._icon.run()

    def _sync_loop(self):
        """Periodically sync tray icon with heartbeat state."""
        while self._running:
            try:
                self._sync_icon_state()
            except Exception:
                pass
            # Check every 2 seconds
            for _ in range(20):
                if not self._running:
                    return
                threading.Event().wait(0.1)

    def _sync_icon_state(self):
        """Update tray icon color based on heartbeat state."""
        if not self.runtime.heartbeat or not self._icon:
            return

        is_running = self.runtime.heartbeat._running
        is_paused = self.runtime.heartbeat._paused
        is_active = is_running and not is_paused

        # Only update if state changed
        if is_active == self._last_hb_state:
            return

        self._last_hb_state = is_active
        color = "#44BB44" if is_active else "#FF4444"
        self._icon.icon = create_icon_image(
            color=color,
            letter=self.runtime.config.di_letter,
        )
        logger.debug(f"Tray icon synced: {'ON' if is_active else 'OFF'}")

    def _on_status(self, icon, item):
        """Show status notification."""
        status = self.runtime.heartbeat.get_status() if self.runtime.heartbeat else {}
        mood = self.runtime.identity.get_mood() if self.runtime.identity else "unknown"
        hb = "ON" if status.get("running") else "OFF"
        interval = status.get("last_interval_minutes", "?")

        msg = f"Heartbeat: {hb} ({interval}min)\nMood: {mood}"
        logger.info(msg)

    def _on_toggle_heartbeat(self, icon, item):
        """Toggle heartbeat on/off."""
        if not self.runtime.heartbeat:
            return

        is_on = self.runtime.heartbeat.toggle()
        color = "#44BB44" if is_on else "#FF4444"
        self._icon.icon = create_icon_image(
            color=color,
            letter=self.runtime.config.di_letter,
        )
        self._last_hb_state = is_on
        logger.info(f"Heartbeat {'ON' if is_on else 'OFF'}")

    def _on_memory_count(self, icon, item):
        """Show memory count."""
        logger.info("Memory count requested")

    def _on_memory_recent(self, icon, item):
        """Show recent memories."""
        logger.info("Recent memories requested")

    def _on_skills_count(self, icon, item):
        """Show skills count."""
        logger.info("Skills count requested")

    def _on_skills_list(self, icon, item):
        """Show skills list."""
        logger.info("Skills list requested")

    def _on_quit(self, icon, item):
        """Quit the application."""
        self._running = False
        icon.stop()
        # Signal runtime to stop
        if self.runtime._running:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.runtime.stop())
            )
