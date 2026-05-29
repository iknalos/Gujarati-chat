"""Smoke test for the dialog-loop listener/transcript plumbing.

We don't drive the recorder/TTS — those need real audio. We just verify
that the listener APIs notify subscribers correctly, which is what the
GUI relies on.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dialog_loop import DialogLoop, DialogTranscriptEntry


def test_state_listener_called_on_set_state():
    loop = DialogLoop(project_dir=Path("/tmp"))
    seen: list[str] = []
    loop.add_state_listener(seen.append)
    loop._set_state("listening")
    loop._set_state("thinking")
    loop._set_state("thinking")  # duplicate must be deduped
    loop._set_state("idle")
    assert seen == ["listening", "thinking", "idle"]


def test_transcript_listener_called_on_emit():
    loop = DialogLoop(project_dir=Path("/tmp"))
    seen: list[DialogTranscriptEntry] = []
    loop.add_transcript_listener(seen.append)
    loop._emit_transcript("user", "આ ગુજરાતી છે.")
    loop._emit_transcript("assistant", "હા, હું સાંભળું છું.")
    assert [e.role for e in seen] == ["user", "assistant"]
    assert seen[0].text == "આ ગુજરાતી છે."
    assert seen[1].text == "હા, હું સાંભળું છું."


def test_listener_exceptions_do_not_break_loop():
    loop = DialogLoop(project_dir=Path("/tmp"))
    good_calls: list[str] = []

    def bad(_):
        raise RuntimeError("listener exploded")

    loop.add_state_listener(bad)
    loop.add_state_listener(good_calls.append)
    loop._set_state("listening")
    assert good_calls == ["listening"]


def test_wake_and_stop_set_their_events():
    loop = DialogLoop(project_dir=Path("/tmp"))
    assert not loop._wake_event.is_set()
    loop.wake()
    assert loop._wake_event.is_set()
    assert not loop._dialog_end_event.is_set()
    loop.stop_dialog()
    assert loop._dialog_end_event.is_set()
