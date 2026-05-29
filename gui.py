"""Tkinter window for GujaratiClaude.

Three visual states (idle/listening/thinking/speaking) shown via a colored
indicator dot, plus a scrolling transcript pane showing the last N turns in
Gujarati script. Updates from background threads are marshalled through a
``queue.Queue`` and drained by an ``after()`` poll in the Tk mainloop —
Tkinter is not thread-safe.

The window is always-on-top, ~420×320, with two buttons: Wake (manual
trigger for testing without a wake word) and Stop (end current dialog).
"""
from __future__ import annotations

import tkinter as tk
from queue import Empty, Queue
from tkinter import font as tkfont
from typing import Callable, Optional

from dialog_loop import DialogTranscriptEntry


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
        on_text_submit: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_wake = on_wake
        self._on_stop = on_stop
        self._on_close = on_close
        self._on_text_submit = on_text_submit

        self._events: Queue[tuple[str, object]] = Queue()
        self._max_transcript_chars = 4000

        self.root = tk.Tk()
        self.root.title("GujaratiClaude")
        self.root.geometry("420x320")
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", self._handle_close)

        # Prefer a Gujarati-capable font; Tk will fall back if absent.
        gu_font = tkfont.Font(family="Nirmala UI", size=12)

        top = tk.Frame(self.root)
        top.pack(side="top", fill="x", padx=10, pady=8)
        self._dot = tk.Canvas(top, width=24, height=24, highlightthickness=0)
        self._dot_id = self._dot.create_oval(2, 2, 22, 22, fill=_STATE_COLOR["idle"], outline="")
        self._dot.pack(side="left")
        self._state_label = tk.Label(top, text=_STATE_LABEL["idle"], font=gu_font)
        self._state_label.pack(side="left", padx=8)

        btns = tk.Frame(top)
        btns.pack(side="right")
        tk.Button(btns, text="Wake", command=self._on_wake).pack(side="left", padx=2)
        tk.Button(btns, text="Stop", command=self._on_stop).pack(side="left", padx=2)

        # Optional text-input row (shown only if on_text_submit was given).
        if self._on_text_submit is not None:
            entry_row = tk.Frame(self.root)
            entry_row.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
            self._entry = tk.Entry(entry_row, font=gu_font)
            self._entry.pack(side="left", fill="x", expand=True)
            self._entry.bind("<Return>", lambda _e: self._submit_text())
            tk.Button(entry_row, text="મોકલો", command=self._submit_text).pack(side="right", padx=(6, 0))

        self._transcript = tk.Text(
            self.root, wrap="word", font=gu_font, state="disabled",
            background="#fafafa", borderwidth=1, relief="solid",
        )
        self._transcript.pack(side="bottom", fill="both", expand=True, padx=10, pady=(0, 10))
        self._transcript.tag_configure("user", foreground="#0033cc")
        self._transcript.tag_configure("assistant", foreground="#006600")
        self._transcript.tag_configure("tool", foreground="#888888")

        self.root.after(50, self._drain_events)

    def _submit_text(self) -> None:
        text = self._entry.get().strip()
        if not text or self._on_text_submit is None:
            return
        self._entry.delete(0, "end")
        self._on_text_submit(text)

    # ---- Thread-safe API (callable from any thread) -----------------------

    def push_state(self, state: str) -> None:
        self._events.put(("state", state))

    def push_transcript(self, entry: DialogTranscriptEntry) -> None:
        self._events.put(("transcript", entry))

    # ---- Mainloop helpers -------------------------------------------------

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
        # Cap transcript length so memory doesn't grow without bound.
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
