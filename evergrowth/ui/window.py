"""Modern GUI window for Evergrowth using customtkinter."""

import asyncio
import logging
import threading

import customtkinter as ctk

logger = logging.getLogger("evergrowth.ui.window")


class EvergrowthWindow:
    """
    Modern GUI window for Evergrowth.

    Shows:
    - DI status (name, mood, session count)
    - Heartbeat status and controls
    - Memory and skill counts
    - Quick actions
    """

    def __init__(self, runtime):
        self.runtime = runtime
        self._root = None
        self._running = False
        self._update_task = None

    def start(self):
        """Start the GUI window in a background thread."""
        self._running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        logger.info("GUI window started")

    def stop(self):
        """Stop the GUI window."""
        self._running = False
        if self._root:
            self._root.after(0, self._root.destroy)
        logger.info("GUI window stopped")

    def _run(self):
        """Run the GUI (blocking call in thread)."""
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._root = ctk.CTk()
        self._root.title("Evergrowth")
        self._root.geometry("400x500")
        self._root.resizable(False, False)

        self._create_widgets()
        self._start_update_loop()

        self._root.mainloop()

    def _create_widgets(self):
        """Create the main window widgets."""
        # Header
        header = ctk.CTkLabel(
            self._root,
            text="Evergrowth",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        header.pack(pady=(20, 5))

        subtitle = ctk.CTkLabel(
            self._root,
            text=f"DI: {self.runtime.config.di_name}",
            font=ctk.CTkFont(size=14),
            text_color="gray",
        )
        subtitle.pack(pady=(0, 20))

        # Status frame
        status_frame = ctk.CTkFrame(self._root)
        status_frame.pack(fill="x", padx=20, pady=5)

        self._mood_label = ctk.CTkLabel(
            status_frame,
            text="Mood: neutral",
            font=ctk.CTkFont(size=12),
        )
        self._mood_label.pack(pady=5)

        self._session_label = ctk.CTkLabel(
            status_frame,
            text="Sessions: 0",
            font=ctk.CTkFont(size=12),
        )
        self._session_label.pack(pady=5)

        # Heartbeat frame
        hb_frame = ctk.CTkFrame(self._root)
        hb_frame.pack(fill="x", padx=20, pady=5)

        hb_header = ctk.CTkLabel(
            hb_frame,
            text="Heartbeat",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        hb_header.pack(pady=(10, 5))

        self._hb_status_label = ctk.CTkLabel(
            hb_frame,
            text="Status: OFF",
            font=ctk.CTkFont(size=12),
        )
        self._hb_status_label.pack(pady=2)

        self._hb_interval_label = ctk.CTkLabel(
            hb_frame,
            text="Interval: 30 min",
            font=ctk.CTkFont(size=12),
        )
        self._hb_interval_label.pack(pady=2)

        self._hb_toggle_btn = ctk.CTkButton(
            hb_frame,
            text="Toggle Heartbeat",
            command=self._on_toggle_heartbeat,
        )
        self._hb_toggle_btn.pack(pady=10)

        # Memory/Skills frame
        counts_frame = ctk.CTkFrame(self._root)
        counts_frame.pack(fill="x", padx=20, pady=5)

        self._memory_label = ctk.CTkLabel(
            counts_frame,
            text="Memory: 0 entries",
            font=ctk.CTkFont(size=12),
        )
        self._memory_label.pack(pady=5)

        self._skills_label = ctk.CTkLabel(
            counts_frame,
            text="Skills: 0 learned",
            font=ctk.CTkFont(size=12),
        )
        self._skills_label.pack(pady=5)

        # Quit button
        quit_btn = ctk.CTkButton(
            self._root,
            text="Quit",
            command=self._on_quit,
            fg_color="#FF4444",
            hover_color="#CC3333",
        )
        quit_btn.pack(pady=20)

    def _start_update_loop(self):
        """Start periodic UI updates."""
        def _update():
            if not self._running:
                return
            self._refresh_labels()
            self._root.after(5000, _update)
        self._root.after(1000, _update)

    def _refresh_labels(self):
        """Refresh all labels with current state."""
        try:
            if self.runtime.identity:
                mood = self.runtime.identity.get_mood()
                state = self.runtime.identity._state
                sessions = state.get("session_count", 0)
                self._mood_label.configure(text=f"Mood: {mood}")
                self._session_label.configure(text=f"Sessions: {sessions}")

            if self.runtime.heartbeat:
                status = self.runtime.heartbeat.get_status()
                running = status.get("running", False)
                interval = status.get("last_interval_minutes", "?")
                self._hb_status_label.configure(
                    text=f"Status: {'ON' if running else 'OFF'}"
                )
                self._hb_interval_label.configure(
                    text=f"Interval: {interval} min"
                )
        except Exception as e:
            logger.debug(f"UI update error: {e}")

    def _on_toggle_heartbeat(self):
        """Toggle heartbeat on/off."""
        if not self.runtime.heartbeat:
            return

        if self.runtime.heartbeat._running:
            self.runtime.heartbeat.pause()
        else:
            self.runtime.heartbeat.resume()

    def _on_quit(self):
        """Quit the application."""
        self._running = False
        if self._root:
            self._root.after(0, self._root.destroy)
        if self.runtime._running:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(lambda: asyncio.create_task(self.runtime.stop()))
