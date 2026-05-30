"""Text-only mode: GUI entry box → Claude bridge → GUI transcript.

Bypasses the microphone, Whisper, and IndicF5 entirely. Useful for:
- Verifying Phase 3 (bridge plumbing) before you set up audio
- Using GujaratiClaude on a machine without a CUDA GPU
- Quick testing during development

Run via ``main.py --text``.
"""
from __future__ import annotations

import threading
from pathlib import Path
from queue import Empty
from typing import Callable

import config
from claude_bridge import ClaudeBridge, StreamEvent
from dialog_loop import DialogTranscriptEntry


class TextModeDriver:
    """Lightweight stand-in for DialogLoop that only does text I/O.

    Same listener API as ``DialogLoop`` so the GUI doesn't care which one
    is wired up.
    """

    STATE_IDLE = "idle"
    STATE_THINKING = "thinking"

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir
        self._state_listeners: list[Callable[[str], None]] = []
        self._transcript_listeners: list[Callable[[DialogTranscriptEntry], None]] = []
        self._bridge = ClaudeBridge(
            project_dir=project_dir,
            system_prompt_file=config.GU_SYSTEM_PROMPT_FILE,
            claude_bin=config.CLAUDE_BIN,
            permission_mode=config.PERMISSION_MODE,
            strip_code=False,
        )
        self._started = False
        self._lock = threading.Lock()

    # ---- Same listener API as DialogLoop ----------------------------------

    def add_state_listener(self, fn: Callable[[str], None]) -> None:
        self._state_listeners.append(fn)

    def add_transcript_listener(self, fn: Callable[[DialogTranscriptEntry], None]) -> None:
        self._transcript_listeners.append(fn)

    def _set_state(self, state: str) -> None:
        for fn in list(self._state_listeners):
            try:
                fn(state)
            except Exception:
                pass

    def _emit(self, role: str, text: str) -> None:
        entry = DialogTranscriptEntry(role=role, text=text)
        for fn in list(self._transcript_listeners):
            try:
                fn(entry)
            except Exception:
                pass

    # ---- Driver ----------------------------------------------------------

    def submit_text(self, text: str) -> None:
        """Called by the GUI when the user hits Send. Runs the turn in a
        background thread so the Tk mainloop doesn't freeze."""
        threading.Thread(target=self._run_turn, args=(text,), daemon=True).start()

    def _ensure_started(self) -> None:
        with self._lock:
            if not self._started:
                self._bridge.start()
                self._started = True

    def _run_turn(self, user_text: str) -> None:
        try:
            self._ensure_started()
            self._emit("user", user_text)
            self._set_state(self.STATE_THINKING)
            self._bridge.send(user_text)
            self._drain_until_turn_end()
        finally:
            self._set_state(self.STATE_IDLE)

    def _drain_until_turn_end(self) -> None:
        # 600 s covers long-running tool work like `pnpm install`, `vercel
        # deploy`, large file reads, etc. We rely on the bridge to also
        # close the queue if the subprocess dies (it pushes turn_end with
        # reason=process_exit), so we don't need a tight liveness check.
        q = self._bridge.events()
        while True:
            try:
                ev: StreamEvent = q.get(timeout=600)
            except Empty:
                self._emit("tool", "[bridge: no response for 10 min — giving up]")
                return
            if ev.kind == "text_delta":
                self._emit("assistant", ev.text)
            elif ev.kind == "tool_use":
                d = ev.data or {}
                self._emit("tool", f"[tool {d.get('name','?')}]")
            elif ev.kind == "system":
                d = ev.data or {}
                if d.get("subtype") == "api_retry":
                    self._emit("tool", f"[retry: {d.get('error')}]")
            elif ev.kind == "error":
                d = ev.data or {}
                self._emit("tool", f"[bridge error: {d.get('message')}]")
            elif ev.kind == "turn_end":
                return

    # ---- Compatible-with-DialogLoop no-ops --------------------------------

    def start(self) -> None: ...
    def wake(self) -> None: ...
    def stop_dialog(self) -> None: ...
    def shutdown(self) -> None:
        if self._started:
            self._bridge.close()
