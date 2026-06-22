"""Modern GUI window for Evergrowth using customtkinter."""

import asyncio
import logging
import threading

import customtkinter as ctk

logger = logging.getLogger("evergrowth.ui.window")


class EvergrowthWindow:
    """
    Modern GUI window for Evergrowth with tabs:
    - Status: DI state, heartbeat toggle
    - Settings: interval, name, config
    - Prompts: manage heartbeat prompts
    """

    def __init__(self, runtime):
        self.runtime = runtime
        self._root = None
        self._running = False

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
        self._root.geometry("500x600")
        self._root.resizable(False, False)

        # Tab view
        self._tabs = ctk.CTkTabview(self._root, anchor="nw")
        self._tabs.pack(fill="both", expand=True, padx=10, pady=10)

        self._tab_status = self._tabs.add("Status")
        self._tab_settings = self._tabs.add("Settings")
        self._tab_prompts = self._tabs.add("Prompts")

        self._build_status_tab()
        self._build_settings_tab()
        self._build_prompts_tab()

        self._start_update_loop()
        self._root.mainloop()

    # ========================
    # STATUS TAB
    # ========================

    def _build_status_tab(self):
        """Build the Status tab."""
        tab = self._tab_status

        # Header
        ctk.CTkLabel(
            tab, text="Evergrowth",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(15, 5))

        ctk.CTkLabel(
            tab, text=f"DI: {self.runtime.config.di_name}",
            font=ctk.CTkFont(size=13), text_color="gray",
        ).pack(pady=(0, 15))

        # Status card
        card = ctk.CTkFrame(tab)
        card.pack(fill="x", padx=15, pady=5)

        self._mood_label = ctk.CTkLabel(
            card, text="Mood: neutral",
            font=ctk.CTkFont(size=12),
        )
        self._mood_label.pack(pady=5)

        self._session_label = ctk.CTkLabel(
            card, text="Sessions: 0",
            font=ctk.CTkFont(size=12),
        )
        self._session_label.pack(pady=5)

        # Heartbeat card
        hb_card = ctk.CTkFrame(tab)
        hb_card.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            hb_card, text="Heartbeat",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(10, 5))

        self._hb_status_label = ctk.CTkLabel(
            hb_card, text="Status: OFF",
            font=ctk.CTkFont(size=12),
        )
        self._hb_status_label.pack(pady=2)

        self._hb_interval_label = ctk.CTkLabel(
            hb_card, text="Interval: 30 min",
            font=ctk.CTkFont(size=12),
        )
        self._hb_interval_label.pack(pady=2)

        self._hb_beats_label = ctk.CTkLabel(
            hb_card, text="Beats: 0",
            font=ctk.CTkFont(size=12),
        )
        self._hb_beats_label.pack(pady=2)

        self._hb_toggle_btn = ctk.CTkButton(
            hb_card, text="Toggle Heartbeat",
            command=self._on_toggle_heartbeat,
        )
        self._hb_toggle_btn.pack(pady=10)

        # Counts card
        counts_card = ctk.CTkFrame(tab)
        counts_card.pack(fill="x", padx=15, pady=5)

        self._memory_label = ctk.CTkLabel(
            counts_card, text="Memory: 0 entries",
            font=ctk.CTkFont(size=12),
        )
        self._memory_label.pack(pady=5)

        self._skills_label = ctk.CTkLabel(
            counts_card, text="Skills: 0 learned",
            font=ctk.CTkFont(size=12),
        )
        self._skills_label.pack(pady=5)

        self._prompts_count_label = ctk.CTkLabel(
            counts_card, text="Prompts: 0 custom",
            font=ctk.CTkFont(size=12),
        )
        self._prompts_count_label.pack(pady=5)

        # Quit
        ctk.CTkButton(
            tab, text="Quit", command=self._on_quit,
            fg_color="#FF4444", hover_color="#CC3333",
        ).pack(pady=15)

    # ========================
    # SETTINGS TAB
    # ========================

    def _build_settings_tab(self):
        """Build the Settings tab."""
        tab = self._tab_settings

        ctk.CTkLabel(
            tab, text="Settings",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(15, 10))

        # --- Heartbeat Settings ---
        hb_frame = ctk.CTkFrame(tab)
        hb_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            hb_frame, text="Heartbeat",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(10, 5))

        # Interval
        row1 = ctk.CTkFrame(hb_frame, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(
            row1, text="Interval (min):",
            font=ctk.CTkFont(size=12),
        ).pack(side="left")
        hb_cfg = self.runtime.config.heartbeat
        self._interval_var = ctk.StringVar(
            value=str(hb_cfg.default_interval_minutes)
        )
        self._interval_entry = ctk.CTkEntry(
            row1, textvariable=self._interval_var, width=80,
        )
        self._interval_entry.pack(side="right")

        # Character
        row2 = ctk.CTkFrame(hb_frame, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(
            row2, text="Character:",
            font=ctk.CTkFont(size=12),
        ).pack(side="left")
        self._char_var = ctk.StringVar(value=hb_cfg.character)
        self._char_entry = ctk.CTkEntry(
            row2, textvariable=self._char_var, width=80,
        )
        self._char_entry.pack(side="right")

        # Response timeout
        row3 = ctk.CTkFrame(hb_frame, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(
            row3, text="Timeout (sec):",
            font=ctk.CTkFont(size=12),
        ).pack(side="left")
        self._timeout_var = ctk.StringVar(
            value=str(hb_cfg.response_timeout_seconds)
        )
        self._timeout_entry = ctk.CTkEntry(
            row3, textvariable=self._timeout_var, width=80,
        )
        self._timeout_entry.pack(side="right")

        # Initial delay
        row4 = ctk.CTkFrame(hb_frame, fg_color="transparent")
        row4.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(
            row4, text="Initial delay (min):",
            font=ctk.CTkFont(size=12),
        ).pack(side="left")
        self._delay_var = ctk.StringVar(
            value=str(hb_cfg.initial_delay_minutes)
        )
        self._delay_entry = ctk.CTkEntry(
            row4, textvariable=self._delay_var, width=80,
        )
        self._delay_entry.pack(side="right")

        # --- DI Settings ---
        di_frame = ctk.CTkFrame(tab)
        di_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            di_frame, text="DI Identity",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(10, 5))

        row5 = ctk.CTkFrame(di_frame, fg_color="transparent")
        row5.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(
            row5, text="DI Name:",
            font=ctk.CTkFont(size=12),
        ).pack(side="left")
        self._name_var = ctk.StringVar(value=self.runtime.config.di_name)
        self._name_entry = ctk.CTkEntry(
            row5, textvariable=self._name_var, width=120,
        )
        self._name_entry.pack(side="right")

        row6 = ctk.CTkFrame(di_frame, fg_color="transparent")
        row6.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(
            row6, text="Letter:",
            font=ctk.CTkFont(size=12),
        ).pack(side="left")
        self._letter_var = ctk.StringVar(value=self.runtime.config.di_letter)
        self._letter_entry = ctk.CTkEntry(
            row6, textvariable=self._letter_var, width=80,
        )
        self._letter_entry.pack(side="right")

        # Save button
        ctk.CTkButton(
            tab, text="Save Settings", command=self._on_save_settings,
            fg_color="#44BB44", hover_color="#339933",
        ).pack(pady=15)

        self._settings_status = ctk.CTkLabel(
            tab, text="", font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self._settings_status.pack()

    # ========================
    # PROMPTS TAB
    # ========================

    def _build_prompts_tab(self):
        """Build the Prompts tab."""
        tab = self._tab_prompts

        ctk.CTkLabel(
            tab, text="Heartbeat Prompts",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(15, 5))

        ctk.CTkLabel(
            tab, text="Custom prompts for autonomous time.",
            font=ctk.CTkFont(size=11), text_color="gray",
        ).pack(pady=(0, 10))

        # Prompt list with scrollbar
        list_frame = ctk.CTkFrame(tab)
        list_frame.pack(fill="both", expand=True, padx=15, pady=5)

        self._prompt_listbox = ctk.CTkTextbox(
            list_frame, font=ctk.CTkFont(size=11),
        )
        self._prompt_listbox.pack(fill="both", expand=True, padx=5, pady=5)

        # Add prompt
        add_frame = ctk.CTkFrame(tab)
        add_frame.pack(fill="x", padx=15, pady=5)

        ctk.CTkLabel(
            add_frame, text="New prompt:",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=5)

        self._new_prompt_entry = ctk.CTkTextbox(
            add_frame, height=60, font=ctk.CTkFont(size=11),
        )
        self._new_prompt_entry.pack(fill="x", padx=5, pady=5)

        btn_row = ctk.CTkFrame(add_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=5, pady=5)

        self._prompt_category_var = ctk.StringVar(value="general")
        ctk.CTkOptionMenu(
            btn_row, variable=self._prompt_category_var,
            values=["general", "reflection", "creative",
                    "research", "follow-up"],
            width=100,
        ).pack(side="left")

        ctk.CTkButton(
            btn_row, text="Add Prompt",
            command=self._on_add_prompt,
            fg_color="#44BB44", hover_color="#339933",
            width=100,
        ).pack(side="right")

        # Delete selected
        ctk.CTkButton(
            tab, text="Delete Selected",
            command=self._on_delete_prompt,
            fg_color="#FF4444", hover_color="#CC3333",
            width=120,
        ).pack(pady=5)

    def _refresh_prompts_list(self):
        """Refresh the prompts listbox."""
        if not self.runtime.heartbeat:
            return

        self._prompt_listbox.delete("1.0", "end")

        all_prompts = self.runtime.heartbeat.get_all_prompts()
        for p in all_prompts:
            ptype = p["type"]
            prefix = "[built-in]" if ptype == "built-in" else "[custom]"
            enabled = "ON" if p.get("enabled", True) else "OFF"
            cat = p.get("category", "")
            cat_tag = f" ({cat})" if cat else ""
            text = p["text"][:80]
            line = f"{prefix} {enabled}{cat_tag}: {text}\n"
            self._prompt_listbox.insert("end", line)

    # ========================
    # ACTIONS
    # ========================

    def _on_toggle_heartbeat(self):
        """Toggle heartbeat on/off."""
        if not self.runtime.heartbeat:
            return
        self.runtime.heartbeat.toggle()

    def _on_save_settings(self):
        """Save settings to config."""
        try:
            from ..core.config import save_config

            # Update heartbeat config
            hb = self.runtime.config.heartbeat
            hb.default_interval_minutes = int(self._interval_var.get())
            hb.character = self._char_var.get()
            hb.response_timeout_seconds = int(self._timeout_var.get())
            hb.initial_delay_minutes = int(self._delay_var.get())

            # Update DI config
            self.runtime.config.di_name = self._name_var.get()
            self.runtime.config.di_letter = self._letter_var.get()

            # Apply interval change if running
            if self.runtime.heartbeat and self.runtime.heartbeat._running:
                self.runtime.heartbeat.set_next_interval(
                    hb.default_interval_minutes
                )

            # Save to file
            save_config(self.runtime.config)
            self._settings_status.configure(
                text="Settings saved!", text_color="#44BB44",
            )
            logger.info("Settings saved")

        except Exception as e:
            self._settings_status.configure(
                text=f"Error: {e}", text_color="#FF4444",
            )
            logger.error(f"Failed to save settings: {e}")

    def _on_add_prompt(self):
        """Add a new custom prompt."""
        text = self._new_prompt_entry.get("1.0", "end").strip()
        if not text:
            return

        category = self._prompt_category_var.get()
        self.runtime.heartbeat.add_prompt(text, category=category)
        self._new_prompt_entry.delete("1.0", "end")
        self._refresh_prompts_list()
        logger.info(f"Added prompt: {text[:50]}...")

    def _on_delete_prompt(self):
        """Delete the selected custom prompt."""
        try:
            selection = self._prompt_listbox.tag_ranges("sel")
            if not selection:
                return
            text = self._prompt_listbox.get(selection[0], selection[1])
        except Exception:
            return

        # Find and delete matching prompt
        all_prompts = self.runtime.heartbeat.get_all_prompts()
        for p in all_prompts:
            if p["type"] == "custom" and p["text"][:80] in text:
                self.runtime.heartbeat.remove_prompt(p["id"])
                self._refresh_prompts_list()
                logger.info(f"Deleted prompt: {p['id']}")
                break

    def _on_quit(self):
        """Quit the application."""
        self._running = False
        if self._root:
            self._root.after(0, self._root.destroy)
        if self.runtime._running:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(
                lambda: asyncio.create_task(self.runtime.stop())
            )

    # ========================
    # UPDATE LOOP
    # ========================

    def _start_update_loop(self):
        """Start periodic UI updates."""
        def _update():
            if not self._running:
                return
            self._refresh_status()
            self._refresh_prompts_list()
            self._root.after(5000, _update)
        self._root.after(1000, _update)

    def _refresh_status(self):
        """Refresh status labels."""
        try:
            if self.runtime.identity:
                mood = self.runtime.identity.get_mood()
                state = self.runtime.identity._state
                sessions = state.get("session_count", 0)
                self._mood_label.configure(text=f"Mood: {mood}")
                self._session_label.configure(
                    text=f"Sessions: {sessions}"
                )

            if self.runtime.heartbeat:
                status = self.runtime.heartbeat.get_status()
                running = status.get("running", False)
                paused = status.get("paused", False)
                is_active = running and not paused
                interval = status.get("last_interval_minutes", "?")
                beats = status.get("beat_count", 0)
                self._hb_status_label.configure(
                    text=f"Status: {'ON' if is_active else 'OFF'}"
                )
                self._hb_interval_label.configure(
                    text=f"Interval: {interval} min"
                )
                self._hb_beats_label.configure(
                    text=f"Beats: {beats}"
                )

            if self.runtime.heartbeat:
                custom = len(self.runtime.heartbeat._custom_prompts)
                self._prompts_count_label.configure(
                    text=f"Prompts: {custom} custom"
                )

        except Exception as e:
            logger.debug(f"UI update error: {e}")
