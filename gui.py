"""Unified GujaratiClaude dashboard — single Tk window with three regions:

  ┌─ Top: state indicator + title + Wake / Stop ───────────────────┐
  │                                                                 │
  │   Chat transcript (left)       │   Outputs panel (right)         │
  │   - User & assistant lines     │   - File list                   │
  │   - Auto-scrolls               │   - Image preview               │
  │                                │                                 │
  ├─ Bottom: text entry + Send (text mode only) ─────────────────────┤
  └──────────────────────────────────────────────────────────────────┘

Replaces the older split-window layout (separate Toplevel for outputs).
Wake/Stop buttons stay visible even in text mode — they're cheap and the
voice flow may share this same window once wake-word/STT are wired up.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable, Optional

from dialog_loop import DialogTranscriptEntry
from outputs_panel import OutputsPanel


_STATE_COLOR = {
    "idle": "#888888",
    "listening": "#ff3030",
    "thinking": "#ff9900",
    "speaking": "#30c030",
}
_STATE_LABEL = {
    "idle": "નિષ્ક્રિય",
    "listening": "સાંભળી રહ્યું છે",
    "thinking": "વિચારી રહ્યું છે",
    "speaking": "બોલી રહ્યું છે",
}


class GujaratiClaudeGUI:
    def __init__(
        self,
        on_wake: Callable[[], None],
        on_stop: Callable[[], None],
        on_close: Callable[[], None],
        outputs_dir: Path,
        on_text_submit: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_wake = on_wake
        self._on_stop = on_stop
        self._on_close = on_close
        self._on_text_submit = on_text_submit

        self._events: Queue[tuple[str, object]] = Queue()
        self._max_transcript_chars = 8000

        self.root = tk.Tk()
        self.root.title("GujaratiClaude")
        self.root.geometry("1100x680")
        self.root.minsize(820, 480)
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)

        gu_font = tkfont.Font(family="Nirmala UI", size=12)
        title_font = tkfont.Font(family="Segoe UI", size=13, weight="bold")

        # ---- Header bar ------------------------------------------------
        header = tk.Frame(self.root, padx=12, pady=8)
        header.pack(side="top", fill="x")

        self._dot = tk.Canvas(header, width=22, height=22, highlightthickness=0)
        self._dot_id = self._dot.create_oval(2, 2, 20, 20,
                                             fill=_STATE_COLOR["idle"], outline="")
        self._dot.pack(side="left")
        self._state_label = tk.Label(header, text=_STATE_LABEL["idle"], font=gu_font)
        self._state_label.pack(side="left", padx=(8, 0))

        tk.Label(header, text="GujaratiClaude", font=title_font).pack(
            side="left", padx=(24, 0)
        )

        btns = tk.Frame(header)
        btns.pack(side="right")
        tk.Button(btns, text="Wake", command=self._on_wake).pack(side="left", padx=2)
        tk.Button(btns, text="Stop", command=self._on_stop).pack(side="left", padx=2)

        # ---- Bottom entry row (text mode only) -------------------------
        if self._on_text_submit is not None:
            entry_row = tk.Frame(self.root)
            entry_row.pack(side="bottom", fill="x", padx=12, pady=(0, 10))
            self._entry = tk.Entry(entry_row, font=gu_font)
            self._entry.pack(side="left", fill="x", expand=True, ipady=4)
            self._entry.bind("<Return>", lambda _e: self._submit_text())
            tk.Button(entry_row, text="મોકલો", command=self._submit_text).pack(
                side="right", padx=(8, 0), ipadx=6
            )

        # ---- Main split: chat (left) | outputs (right) -----------------
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(side="bottom", fill="both", expand=True, padx=12, pady=(0, 10))

        chat_frame = tk.Frame(paned)
        self._transcript = tk.Text(
            chat_frame, wrap="word", font=gu_font, state="disabled",
            background="#fafafa", borderwidth=1, relief="solid",
            padx=8, pady=8,
        )
        sb_chat = ttk.Scrollbar(chat_frame, orient="vertical",
                                command=self._transcript.yview)
        self._transcript.configure(yscrollcommand=sb_chat.set)
        self._transcript.pack(side="left", fill="both", expand=True)
        sb_chat.pack(side="right", fill="y")
        self._transcript.tag_configure("user", foreground="#0033cc")
        self._transcript.tag_configure("assistant", foreground="#006600")
        self._transcript.tag_configure("tool", foreground="#888888")
        paned.add(chat_frame, weight=3)

        self.outputs_panel = OutputsPanel(paned, outputs_dir)
        paned.add(self.outputs_panel, weight=2)

        if self._on_text_submit is not None:
            self._entry.focus_set()

        self.root.after(50, self._drain_events)

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
        color = _STATE_COLOR.get(state, "#888888")
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
