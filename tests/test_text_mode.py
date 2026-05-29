"""End-to-end test of TextModeDriver against the fake_claude subprocess.

This is the closest we can get on Linux to verifying the full path the
Windows user will hit when they run ``launch.bat --text`` and type a
prompt:

    GUI -> TextModeDriver.submit_text -> ClaudeBridge.send
    fake_claude subprocess emits stream_event deltas
    ClaudeBridge reader -> ResponseFilter -> text_delta StreamEvent
    TextModeDriver._drain -> transcript_listener('assistant', sentence)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from text_mode import TextModeDriver
from dialog_loop import DialogTranscriptEntry


def test_text_mode_end_to_end_with_fake_claude(monkeypatch):
    fake = Path(__file__).resolve().parents[1] / "tools" / "fake_claude_shim.sh"
    assert fake.exists(), "fake_claude_shim.sh must exist for this test"

    import config
    monkeypatch.setattr(config, "CLAUDE_BIN", str(fake))

    driver = TextModeDriver(project_dir=Path("/tmp"))
    transcript: list[DialogTranscriptEntry] = []
    states: list[str] = []
    driver.add_transcript_listener(transcript.append)
    driver.add_state_listener(states.append)

    driver.submit_text("WEE-Discount-Tracker ફોલ્ડરમાં કઈ ફાઇલો છે?")

    # The submit runs in a background thread; wait up to 8 s for turn_end.
    deadline = time.time() + 8
    while time.time() < deadline:
        if any(e.role == "assistant" for e in transcript) and "idle" in states:
            break
        time.sleep(0.05)

    driver.shutdown()

    # We should see at least one user entry and one assistant sentence.
    roles = [e.role for e in transcript]
    assert "user" in roles
    assert "assistant" in roles
    # State transitions: thinking -> idle (idle may come after assistant)
    assert "thinking" in states
    assert "idle" in states
