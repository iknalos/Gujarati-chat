"""Text-only mode: GUI entry box → Claude bridge → GUI transcript.

Bypasses the microphone, Whisper, and IndicF5 entirely. Useful for:
- Verifying the bridge plumbing before you set up audio
- Using GujaratiClaude on a machine without a CUDA GPU
- Quick testing during development

Persists conversation history (visual transcript + Claude session_id) via
``history.py`` so the user can close the app and pick up where they left off.

Run via ``main.py --text``.
"""
from __future__ import annotations

import threading
from pathlib import Path
from queue import Empty
from typing import Callable

import config
import history as history_mod
from claude_bridge import ClaudeBridge, StreamEvent
from dialog_loop import DialogTranscriptEntry


def _format_tool_use(block: dict) -> str:
    """Turn a tool_use stream block into a one-line human description.

    Replaces the previous cryptic ``[tool Bash]`` tag with the actual
    command / file path so the user can see what Claude is doing in
    real time, the same way Claude Code's terminal UI shows it.
    """
    name = block.get("name", "?")
    inp = block.get("input") or {}

    def short(s: str, n: int = 90) -> str:
        s = str(s).split("\n", 1)[0].strip()
        return s if len(s) <= n else s[: n - 1] + "…"

    if name == "Bash":
        return f"⚡  {short(inp.get('command', ''))}"
    if name == "Read":
        return f"📖  Read {short(inp.get('file_path', '?'), 100)}"
    if name == "Write":
        return f"✏️  Write {short(inp.get('file_path', '?'), 100)}"
    if name == "Edit":
        return f"✏️  Edit {short(inp.get('file_path', '?'), 100)}"
    if name == "Glob":
        return f"🔍  Glob {short(inp.get('pattern', '?'))}"
    if name == "Grep":
        return f"🔍  Grep {short(inp.get('pattern', '?'))}"
    if name == "LS":
        return f"📂  LS {short(inp.get('path', '?'), 100)}"
    if name == "WebSearch":
        return f"🌐  Search: {short(inp.get('query', '?'))}"
    if name == "WebFetch":
        return f"🌐  Fetch: {short(inp.get('url', '?'), 100)}"
    if name == "Task":
        return f"🤖  Task: {short(inp.get('description', '?'))}"
    return f"⚙️  {name}"


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

        # Load persisted history. If this project_dir differs from what we
        # saved last time, we still resume the same Claude session but the
        # visual transcript replay is mainly useful for the same project.
        self._history = history_mod.load()
        resume_id = self._history.session_id

        self._bridge = ClaudeBridge(
            project_dir=project_dir,
            system_prompt_file=config.GU_SYSTEM_PROMPT_FILE,
            claude_bin=config.CLAUDE_BIN,
            permission_mode=config.PERMISSION_MODE,
            strip_code=False,
            resume_session_id=resume_id,
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

    def _emit(self, role: str, text: str, record: bool = True) -> None:
        entry = DialogTranscriptEntry(role=role, text=text)
        for fn in list(self._transcript_listeners):
            try:
                fn(entry)
            except Exception:
                pass
        # Record real user/assistant turns into history; skip transient tool
        # tags ([tool Bash], [bridge error: ...], etc.) — those would clutter
        # the saved transcript.
        if record and role in ("user", "assistant"):
            self._history.append(role, text)

    # ---- Replay on startup ------------------------------------------------

    def replay_history(self) -> None:
        """Push every saved entry into the GUI as a faint, non-recording emit.

        Caller invokes this AFTER listeners are registered (otherwise the
        entries go nowhere). The bridge isn't started yet — replay is purely
        cosmetic; Claude's own memory is resumed via --resume.
        """
        if not self._history.transcript:
            return
        # Header marker so the user sees where the previous conversation ends
        self._emit("tool", "── પાછલી વાતચીત / previous conversation ──", record=False)
        for e in self._history.transcript:
            self._emit(e.role, e.text, record=False)
        self._emit("tool", "── નવી વાતચીત / new conversation ──", record=False)

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
        # deploy`, large file reads, etc. The bridge pushes turn_end with
        # reason=process_exit if the subprocess dies, so no tight liveness
        # check is needed.
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
                self._emit("tool", _format_tool_use(ev.data or {}))
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

    # ---- Clear / reset ----------------------------------------------------

    def clear_history(self) -> None:
        """Wipe persisted transcript AND force a fresh Claude session next turn.

        The currently-running ``claude`` subprocess (if any) is closed so the
        next user message spawns a new one without ``--resume`` — Claude
        starts with empty memory just like a first-ever run.
        """
        self._history = history_mod.History()
        history_mod.save(self._history)
        if self._started:
            try:
                self._bridge.close()
            except Exception:
                pass
            self._bridge.resume_session_id = None
            self._bridge.observed_session_id = None
            self._started = False

    def shutdown(self) -> None:
        if self._started:
            self._bridge.close()
        # Persist whatever the bridge observed (will be None if we never sent
        # a turn this run, in which case the saved id from last launch sticks).
        if self._bridge.observed_session_id:
            self._history.session_id = self._bridge.observed_session_id
        self._history.project_dir = str(self._project_dir)
        history_mod.save(self._history)
