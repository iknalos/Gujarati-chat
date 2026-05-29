"""The conversational state machine.

Owns the STT recorder, the persistent ClaudeBridge, and the TTS stream.
Driven by the wake-word event and the GUI's "stop" button. Runs in its
own thread so the GUI mainloop stays responsive.

States:
    IDLE      — waiting for wake word
    LISTENING — recording user speech
    THINKING  — bridge has the user turn; waiting for first text_delta
    SPEAKING  — TTS is playing; we keep streaming sentences in
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty
from typing import Callable, Optional

import config
from claude_bridge import ClaudeBridge, StreamEvent


@dataclass
class DialogTranscriptEntry:
    role: str   # "user" or "assistant" or "tool"
    text: str


class DialogLoop:
    """Run the record → STT → Claude → TTS pipeline.

    Public API used by the GUI:
        loop.wake()                     — fired by wake word
        loop.stop_dialog()              — user said "stop"
        loop.shutdown()                 — app is closing
        loop.add_state_listener(fn)     — fn(state_name) called on state change
        loop.add_transcript_listener(fn) — fn(DialogTranscriptEntry) called
    """

    STATE_IDLE = "idle"
    STATE_LISTENING = "listening"
    STATE_THINKING = "thinking"
    STATE_SPEAKING = "speaking"

    def __init__(self, project_dir: Path) -> None:
        self._project_dir = project_dir
        self._state = self.STATE_IDLE
        self._state_listeners: list[Callable[[str], None]] = []
        self._transcript_listeners: list[Callable[[DialogTranscriptEntry], None]] = []
        self._wake_event = threading.Event()
        self._dialog_end_event = threading.Event()
        self._shutdown = threading.Event()
        self._thread = threading.Thread(target=self._run, name="dialog-loop", daemon=True)

        self._bridge: Optional[ClaudeBridge] = None
        self._recorder = None
        self._tts = None  # RealtimeTTS TextToAudioStream
        self._tts_engine = None

    # ---- Public API --------------------------------------------------------

    def start(self) -> None:
        self._thread.start()

    def wake(self) -> None:
        self._wake_event.set()

    def stop_dialog(self) -> None:
        self._dialog_end_event.set()

    def shutdown(self) -> None:
        self._shutdown.set()
        self._wake_event.set()        # unblock the loop so it sees shutdown
        self._dialog_end_event.set()
        if self._bridge:
            self._bridge.close()
        if self._tts is not None:
            try:
                self._tts.stop()
            except Exception:
                pass
        if self._recorder is not None:
            try:
                self._recorder.shutdown()
            except Exception:
                pass

    def add_state_listener(self, fn: Callable[[str], None]) -> None:
        self._state_listeners.append(fn)

    def add_transcript_listener(self, fn: Callable[[DialogTranscriptEntry], None]) -> None:
        self._transcript_listeners.append(fn)

    # ---- Lifecycle --------------------------------------------------------

    def _set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        for fn in list(self._state_listeners):
            try:
                fn(state)
            except Exception:
                pass

    def _emit_transcript(self, role: str, text: str) -> None:
        entry = DialogTranscriptEntry(role=role, text=text)
        for fn in list(self._transcript_listeners):
            try:
                fn(entry)
            except Exception:
                pass

    def _ensure_started(self) -> None:
        if self._bridge is None:
            self._bridge = ClaudeBridge(
                project_dir=self._project_dir,
                system_prompt_file=config.GU_SYSTEM_PROMPT_FILE,
                claude_bin=config.CLAUDE_BIN,
                permission_mode=config.PERMISSION_MODE,
            )
            self._bridge.start()
        if self._recorder is None:
            from RealtimeSTT import AudioToTextRecorder
            self._recorder = AudioToTextRecorder(
                model=str(config.WHISPER_CT2_DIR),
                language=config.STT_LANGUAGE,
                compute_type=config.STT_COMPUTE_TYPE,
                silero_sensitivity=config.STT_SILERO_SENSITIVITY,
                post_speech_silence_duration=config.STT_SILENCE_SECS,
                spinner=False,
                use_microphone=True,
            )
        if self._tts is None:
            from RealtimeTTS import TextToAudioStream
            from indic_f5_engine import IndicF5Engine
            self._tts_engine = IndicF5Engine()
            self._tts = TextToAudioStream(self._tts_engine, language="gu")

    def _run(self) -> None:
        while not self._shutdown.is_set():
            self._set_state(self.STATE_IDLE)
            self._wake_event.wait()
            self._wake_event.clear()
            if self._shutdown.is_set():
                break
            try:
                self._ensure_started()
                self._dialog_until_silence()
            except Exception as exc:    # pragma: no cover - I/O paths
                self._emit_transcript("tool", f"[error] {exc!r}")
                time.sleep(1)

    def _dialog_until_silence(self) -> None:
        """Run record→reply→record loops until DIALOG_TIMEOUT_SECS of silence
        or the user says STOP_PHRASE."""
        self._dialog_end_event.clear()
        deadline = time.monotonic() + config.DIALOG_TIMEOUT_SECS
        while not self._dialog_end_event.is_set() and not self._shutdown.is_set():
            self._set_state(self.STATE_LISTENING)
            user_text = self._record_one_turn(deadline)
            if not user_text:
                return
            if config.STOP_PHRASE in user_text.lower() or user_text.strip().lower() == "stop":
                self._emit_transcript("user", user_text)
                return
            self._emit_transcript("user", user_text)
            self._set_state(self.STATE_THINKING)
            assert self._bridge is not None
            self._bridge.send(user_text)
            self._stream_response_to_tts()
            deadline = time.monotonic() + config.DIALOG_TIMEOUT_SECS

    def _record_one_turn(self, deadline: float) -> str:
        """Return the recognized user utterance, or "" on timeout."""
        assert self._recorder is not None
        result: list[str] = []
        # RealtimeSTT exposes both a synchronous text() and a callback model.
        # We use text() with a short outer timeout via threading.
        finished = threading.Event()

        def runner():
            try:
                txt = self._recorder.text()
                if txt:
                    result.append(txt)
            finally:
                finished.set()

        t = threading.Thread(target=runner, daemon=True)
        t.start()
        finished.wait(timeout=max(1.0, deadline - time.monotonic()))
        if not finished.is_set():
            # Silence timeout: tell the recorder we're done.
            try:
                self._recorder.shutdown()
            except Exception:
                pass
            self._recorder = None
            return ""
        return result[0] if result else ""

    def _stream_response_to_tts(self) -> None:
        """Drain bridge events until turn_end; feed text_delta sentences to TTS."""
        assert self._bridge is not None and self._tts is not None
        q = self._bridge.events()
        started_speaking = False
        while not self._shutdown.is_set():
            try:
                ev: StreamEvent = q.get(timeout=60)
            except Empty:
                self._emit_transcript("tool", "[bridge: no response for 60 s]")
                return
            if ev.kind == "text_delta":
                if not started_speaking:
                    started_speaking = True
                    self._set_state(self.STATE_SPEAKING)
                self._emit_transcript("assistant", ev.text)
                self._tts.feed(ev.text)
                if not self._tts.is_playing():
                    self._tts.play_async()
            elif ev.kind == "tool_use":
                d = ev.data or {}
                self._emit_transcript("tool", f"[tool {d.get('name','?')}]")
            elif ev.kind == "tool_result":
                pass  # surfaced visually elsewhere; not spoken
            elif ev.kind == "system":
                d = ev.data or {}
                if d.get("subtype") == "api_retry":
                    self._emit_transcript("tool", f"[retry: {d.get('error')}]")
            elif ev.kind == "error":
                d = ev.data or {}
                self._emit_transcript("tool", f"[bridge error: {d.get('message')}]")
            elif ev.kind == "turn_end":
                # Wait for TTS to finish playing the last sentence.
                try:
                    while self._tts.is_playing():
                        time.sleep(0.1)
                except Exception:
                    pass
                return
