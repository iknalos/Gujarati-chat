"""Unified GujaratiClaude dashboard — single Tk window, modern Sun Valley theme:

  ┌─ Header: state dot + title + Wake / Stop ──────────────────────┐
  │                                                                 │
  │   Chat transcript (left)        │  Outputs panel (right)        │
  │   - User & assistant turns      │  - File list                  │
  │   - Auto-scrolls                │  - Image / HTML preview       │
  │                                 │                               │
  ├─ Quick-action buttons row ─────────────────────────────────────┤
  ├─ Bottom: text entry + Send (text mode only) ───────────────────┤
  └─────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable, Optional

import sv_ttk

from dialog_loop import DialogTranscriptEntry
from outputs_panel import OutputsPanel


_STATE_COLOR = {
    "idle":      "#6e7681",
    "listening": "#ff4d4d",
    "thinking":  "#ffa726",
    "speaking":  "#4caf50",
}
_STATE_LABEL = {
    "idle":      "નિષ્ક્રિય",
    "listening": "સાંભળી રહ્યું છે",
    "thinking":  "વિચારી રહ્યું છે",
    "speaking":  "બોલી રહ્યું છે",
}

# Dark-theme colors for the tk.Text widget (which sv_ttk doesn't style for us).
_DARK_TRANSCRIPT_BG = "#1e1e1e"
_DARK_TRANSCRIPT_FG = "#e8e8e8"
_DARK_USER_FG       = "#7eb6ff"
_DARK_ASSISTANT_FG  = "#7ee787"
_DARK_TOOL_FG       = "#9aa0a6"

# Quick-action templates. (__CLEAR__ is a special sentinel: clears transcript.)
QUICK_ACTIONS: list[tuple[str, str, str]] = [
    ("📊", "ચાર્ટ",   "આ ફોલ્ડરમાં Excel/CSV ફાઇલ વાંચીને chart બનાવો અને outputs માં save કરો."),
    ("📁", "ફાઇલો",   "આ ફોલ્ડરમાં કઈ ફાઇલો છે? યાદી આપો."),
    ("⚡", "React",   "એક new React app બનાવો અને localhost પર ચાલુ કરો."),
    ("🚀", "Deploy",  "આ project ને Vercel પર deploy કરો."),
    ("🐙", "GitHub",  "આ project માટે GitHub પર નવો repo બનાવો અને push કરો."),
    ("🧹", "Clear",   "__CLEAR__"),
]


class GujaratiClaudeGUI:
    def __init__(
        self,
        on_wake: Callable[[], None],
        on_stop: Callable[[], None],
        on_close: Callable[[], None],
        outputs_dir: Path,
        on_text_submit: Optional[Callable[[str], None]] = None,
        theme: str = "dark",
    ) -> None:
        self._on_wake = on_wake
        self._on_stop = on_stop
        self._on_close = on_close
        self._on_text_submit = on_text_submit

        self._events: Queue[tuple[str, object]] = Queue()
        self._max_transcript_chars = 12000

        self.root = tk.Tk()
        self.root.title("GujaratiClaude")
        self.root.geometry("1180x720")
        self.root.minsize(900, 540)
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)

        sv_ttk.set_theme(theme)

        gu_font     = tkfont.Font(family="Nirmala UI", size=13)
        title_font  = tkfont.Font(family="Segoe UI",   size=15, weight="bold")
        state_font  = tkfont.Font(family="Nirmala UI", size=12)
        action_font = tkfont.Font(family="Nirmala UI", size=10)

        # ---- Header bar ------------------------------------------------
        header = ttk.Frame(self.root, padding=(14, 10))
        header.pack(side="top", fill="x")

        self._dot = tk.Canvas(header, width=22, height=22, highlightthickness=0,
                              background=self._tk_bg())
        self._dot_id = self._dot.create_oval(2, 2, 20, 20,
                                             fill=_STATE_COLOR["idle"], outline="")
        self._dot.pack(side="left")
        self._state_label = ttk.Label(header, text=_STATE_LABEL["idle"], font=state_font)
        self._state_label.pack(side="left", padx=(8, 0))

        ttk.Label(header, text="GujaratiClaude", font=title_font).pack(
            side="left", padx=(26, 0)
        )

        btns = ttk.Frame(header)
        btns.pack(side="right")
        ttk.Button(btns, text="Wake", command=self._on_wake, width=8).pack(side="left", padx=3)
        ttk.Button(btns, text="Stop", command=self._on_stop, width=8).pack(side="left", padx=3)

        # ---- Bottom: entry row (text mode only) ------------------------
        if self._on_text_submit is not None:
            entry_row = ttk.Frame(self.root, padding=(14, 0, 14, 12))
            entry_row.pack(side="bottom", fill="x")
            self._entry = ttk.Entry(entry_row, font=gu_font)
            self._entry.pack(side="left", fill="x", expand=True, ipady=6)
            self._entry.bind("<Return>", lambda _e: self._submit_text())
            ttk.Button(entry_row, text="મોકલો", command=self._submit_text, width=10).pack(
                side="right", padx=(10, 0)
            )

            # ---- Quick-action buttons (just above entry) ---------------
            actions_row = ttk.Frame(self.root, padding=(14, 6, 14, 4))
            actions_row.pack(side="bottom", fill="x")
            ttk.Label(actions_row, text="ઝડપી:", font=action_font).pack(side="left", padx=(0, 8))
            for emoji, label, template in QUICK_ACTIONS:
                btn_text = f"{emoji} {label}"
                ttk.Button(
                    actions_row, text=btn_text,
                    command=lambda t=template: self._quick_action(t),
                ).pack(side="left", padx=3)

        # ---- Main split: chat (left) | outputs (right) -----------------
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(side="bottom", fill="both", expand=True, padx=14, pady=(0, 6))

        chat_frame = ttk.Frame(paned)
        self._transcript = tk.Text(
            chat_frame, wrap="word", font=gu_font, state="disabled",
            background=_DARK_TRANSCRIPT_BG, foreground=_DARK_TRANSCRIPT_FG,
            insertbackground=_DARK_TRANSCRIPT_FG,
            borderwidth=0, relief="flat", padx=12, pady=10,
        )
        sb_chat = ttk.Scrollbar(chat_frame, orient="vertical",
                                command=self._transcript.yview)
        self._transcript.configure(yscrollcommand=sb_chat.set)
        self._transcript.pack(side="left", fill="both", expand=True)
        sb_chat.pack(side="right", fill="y")
        self._transcript.tag_configure("user",      foreground=_DARK_USER_FG,
                                       spacing1=4, spacing3=4)
        self._transcript.tag_configure("assistant", foreground=_DARK_ASSISTANT_FG,
                                       spacing1=2, spacing3=2)
        self._transcript.tag_configure("tool",      foreground=_DARK_TOOL_FG,
                                       font=action_font)
        paned.add(chat_frame, weight=3)

        self.outputs_panel = OutputsPanel(paned, outputs_dir)
        paned.add(self.outputs_panel, weight=2)

        # Match the canvas dot's background to the theme.
        self.root.after(0, lambda: self._dot.configure(background=self._tk_bg()))

        if self._on_text_submit is not None:
            self._entry.focus_set()

        self.root.after(50, self._drain_events)

    def _tk_bg(self) -> str:
        """Sun Valley's themed background color for tk (non-ttk) widgets."""
        try:
            return ttk.Style().lookup("TFrame", "background") or "#202020"
        except tk.TclError:
            return "#202020"

    def _quick_action(self, template: str) -> None:
        if template == "__CLEAR__":
            self._transcript.configure(state="normal")
            self._transcript.delete("1.0", "end")
            self._transcript.configure(state="disabled")
            return
        if not hasattr(self, "_entry"):
            return
        self._entry.delete(0, "end")
        self._entry.insert(0, template)
        self._entry.focus_set()
        self._entry.icursor("end")

    def _submit_text(self) -> None:
        text = self._entry.get().strip()
        if not text or self._on_text_submit is None:
            return
        self._entry.delete(0, "end")
        self._on_text_submit(text)

    # ---- Thread-safe API -------------------------------------------------

    def push_state(self, state: str) -> None:
        self._events.put(("state", state))

    def push_transcript(self, entry: DialogTranscriptEntry) -> None:
        self._events.put(("transcript", entry))

    # ---- Mainloop helpers ------------------------------------------------

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "state":
                    self._set_state_safe(str(payload))
                elif kind == "transcript":
                    assert isinstance(payload, DialogTranscriptEntry)
                    self._append_transcript_safe(payload)
        except Empty:
            pass
        self.root.after(50, self._drain_events)

    def _set_state_safe(self, state: str) -> None:
        color = _STATE_COLOR.get(state, "#6e7681")
        self._dot.itemconfigure(self._dot_id, fill=color)
        self._state_label.configure(text=_STATE_LABEL.get(state, state))

    def _append_transcript_safe(self, entry: DialogTranscriptEntry) -> None:
        self._transcript.configure(state="normal")
        prefix = {"user": "તમે: ", "assistant": "Claude: ", "tool": ""}.get(entry.role, "")
        tag = entry.role if entry.role in ("user", "assistant", "tool") else "tool"
        self._transcript.insert("end", prefix + entry.text + "\n", tag)
        content = self._transcript.get("1.0", "end")
        if len(content) > self._max_transcript_chars:
            excess = len(content) - self._max_transcript_chars
            self._transcript.delete("1.0", f"1.0 + {excess} chars")
        self._transcript.see("end")
        self._transcript.configure(state="disabled")

    def _handle_close(self) -> None:
        try:
            self._on_close()
        finally:
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
