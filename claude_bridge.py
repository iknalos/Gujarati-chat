"""Persistent ``claude -p`` subprocess speaking stream-json on both ends.

One process for the lifetime of the app. Each turn is a single JSON line
written to stdin; replies arrive as newline-delimited JSON on stdout.

Why persistent: avoids ~1-2 s of cold start every turn, and the assistant's
own conversation history is retained without juggling ``--resume`` IDs.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Iterator, Optional

from response_filter import ResponseFilter


@dataclass
class StreamEvent:
    """A normalized event surfaced to the caller. ``kind`` is one of:

    - ``text_delta``  — incremental assistant text (post-filter, sentence-ready)
    - ``tool_use``    — Claude invoked a tool; ``data`` holds the parsed event
    - ``tool_result`` — tool returned
    - ``turn_end``    — assistant finished this turn (flushes filter tail)
    - ``error``       — non-fatal protocol error, ``data['message']`` describes it
    """
    kind: str
    text: str = ""
    data: Optional[dict] = None


class ClaudeBridge:
    def __init__(
        self,
        project_dir: Path,
        system_prompt_file: Path,
        claude_bin: str = "claude",
        permission_mode: str = "acceptEdits",
        strip_code: bool = True,
        resume_session_id: Optional[str] = None,
    ) -> None:
        self.project_dir = project_dir
        self.system_prompt_file = system_prompt_file
        self.claude_bin = claude_bin
        self.permission_mode = permission_mode
        self.resume_session_id = resume_session_id
        self._proc: Optional[subprocess.Popen] = None
        self._filter = ResponseFilter(strip_code=strip_code)
        self._events: "Queue[StreamEvent]" = Queue()
        self._reader_thread: Optional[threading.Thread] = None
        # Updated from the first "system" init event we see on the stream.
        # Callers read this on shutdown to persist for the next launch.
        self.observed_session_id: Optional[str] = None

    # ---- Lifecycle ---------------------------------------------------------

    def start(self) -> None:
        argv = [
            self.claude_bin, "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--append-system-prompt-file", str(self.system_prompt_file),
            "--permission-mode", self.permission_mode,
        ]
        if self.resume_session_id:
            argv += ["--resume", self.resume_session_id]
        # Strip Claude Code's session-detection env vars: when the wrapper
        # itself runs from inside a Claude Code session, those would make
        # the spawned `claude` exit with "cannot be launched inside another
        # Claude Code session".
        child_env = {k: v for k, v in os.environ.items()
                     if k != "CLAUDECODE" and not k.startswith("CLAUDE_CODE_")}
        self._proc = subprocess.Popen(
            argv,
            cwd=str(self.project_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            encoding="utf-8",
            env=child_env,
        )
        self._reader_thread = threading.Thread(
            target=self._read_loop, name="claude-reader", daemon=True
        )
        self._reader_thread.start()

    def close(self) -> None:
        if self._proc and self._proc.stdin and not self._proc.stdin.closed:
            try:
                self._proc.stdin.close()
            except BrokenPipeError:
                pass
        if self._proc:
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    # ---- I/O ---------------------------------------------------------------

    def send(self, user_text: str) -> None:
        """Write a user-turn JSON line to the subprocess stdin. Raises
        ``BrokenPipeError`` if the subprocess has died; callers should
        translate that into an "error" event for the GUI."""
        if not self._proc or not self._proc.stdin:
            raise RuntimeError("ClaudeBridge.start() not called")
        if self._proc.poll() is not None:
            raise BrokenPipeError(
                f"claude subprocess already exited (code={self._proc.returncode})"
            )
        payload = build_user_message(user_text)
        try:
            self._proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise BrokenPipeError(f"failed writing to claude stdin: {exc}") from exc

    def events(self) -> "Queue[StreamEvent]":
        """Thread-safe event queue. Drain from the dialog/GUI threads."""
        return self._events

    # ---- Reader loop -------------------------------------------------------

    def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            for raw_line in self._proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError as exc:
                    self._events.put(StreamEvent("error", data={"message": str(exc), "line": line}))
                    continue
                for normalized in self._normalize(ev):
                    self._events.put(normalized)
        finally:
            # Subprocess closed stdout. Surface a turn_end so any waiter
            # unblocks, plus an error with the exit code + last stderr line
            # for diagnostics.
            exit_code = self._proc.poll() if self._proc else None
            stderr_tail = ""
            try:
                if self._proc and self._proc.stderr:
                    stderr_tail = self._proc.stderr.read() or ""
            except Exception:
                pass
            self._events.put(StreamEvent(
                "error",
                data={
                    "message": f"claude subprocess exited (code={exit_code})",
                    "stderr_tail": stderr_tail[-500:],
                },
            ))
            # Make sure any waiter on turn_end unblocks.
            self._events.put(StreamEvent("turn_end", data={"reason": "process_exit"}))

    def _normalize(self, ev: dict) -> Iterator[StreamEvent]:
        ev_type = ev.get("type")
        # Per-token text deltas (require --include-partial-messages)
        if ev_type == "stream_event":
            event = ev.get("event") or {}
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                for sentence in self._filter.feed(delta.get("text", "")):
                    yield StreamEvent("text_delta", text=sentence)
                return
        # Full assistant/tool/result messages
        if ev_type == "assistant":
            # Inspect content blocks for tool_use entries to surface them in GUI
            msg = ev.get("message") or {}
            for block in msg.get("content") or []:
                if block.get("type") == "tool_use":
                    yield StreamEvent("tool_use", data=block)
            return
        if ev_type == "user":
            # Tool results come back as user messages with tool_result blocks
            msg = ev.get("message") or {}
            for block in msg.get("content") or []:
                if block.get("type") == "tool_result":
                    yield StreamEvent("tool_result", data=block)
            return
        if ev_type == "result":
            # End-of-turn marker
            for sentence in self._filter.flush():
                yield StreamEvent("text_delta", text=sentence)
            yield StreamEvent("turn_end", data=ev)
            return
        if ev_type == "system":
            # init events carry the session_id we'll persist for --resume next launch
            if ev.get("subtype") == "init" and ev.get("session_id"):
                self.observed_session_id = ev.get("session_id")
            yield StreamEvent("system", data=ev)
            return


def build_user_message(text: str) -> dict:
    """The exact JSON shape Claude Code expects on stdin in stream-json mode."""
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        },
    }
