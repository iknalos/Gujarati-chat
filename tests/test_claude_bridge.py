"""Protocol tests for ClaudeBridge using a mock subprocess.

These verify the wire shape Claude Code expects/emits:
- The user-turn JSON we write to stdin is the structure documented in
  the headless guide.
- The events we normalize from stdout cover every documented event type
  we care about.

We do NOT spawn a real ``claude`` process here. Instead, we substitute a
fake ``Popen`` object whose stdout is a list of pre-canned JSONL lines.
"""
from __future__ import annotations

import io
import json
import sys
import threading
from pathlib import Path
from queue import Empty

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_bridge import ClaudeBridge, StreamEvent, build_user_message


# ---- build_user_message ------------------------------------------------------

def test_build_user_message_shape():
    msg = build_user_message("આ ગુજરાતી છે")
    assert msg == {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": "આ ગુજરાતી છે"}],
        },
    }


def test_build_user_message_handles_unicode_through_json():
    msg = build_user_message("આ ગુજરાતી છે")
    encoded = json.dumps(msg, ensure_ascii=False)
    assert "આ ગુજરાતી છે" in encoded


# ---- Event normalization -----------------------------------------------------

class FakeProc:
    """Minimal stand-in for subprocess.Popen used to feed canned stdout."""
    def __init__(self, lines):
        self.stdout = io.StringIO("".join(line + "\n" for line in lines))
        self.stdin = io.StringIO()
        self.stderr = io.StringIO()
        self.killed = False
        self.returncode = 0

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True

    def poll(self):
        # We fake an alive subprocess until the reader has drained stdout.
        # Once stdout is exhausted, treat it as exited.
        return None if self.stdout.tell() < len(self.stdout.getvalue()) else 0


def _drive_bridge_with(lines):
    """Construct a bridge, swap in a FakeProc, run the read loop synchronously,
    and return the StreamEvents produced."""
    b = ClaudeBridge(Path("/tmp"), Path("/tmp/p.txt"))
    b._proc = FakeProc(lines)
    # Run the read loop in the current thread so we can collect events.
    b._read_loop()
    events = []
    while True:
        try:
            events.append(b.events().get_nowait())
        except Empty:
            break
    return events


def test_text_delta_event_is_filtered_into_sentences():
    lines = [
        json.dumps({"type": "stream_event", "event": {"delta": {"type": "text_delta", "text": "નમસ્તે"}}}),
        json.dumps({"type": "stream_event", "event": {"delta": {"type": "text_delta", "text": " જગત."}}}),
        json.dumps({"type": "result"}),
    ]
    events = _drive_bridge_with(lines)
    kinds = [e.kind for e in events]
    assert "text_delta" in kinds
    assert "turn_end" in kinds
    texts = [e.text for e in events if e.kind == "text_delta"]
    assert texts == ["નમસ્તે જગત."]


def test_tool_use_surfaces_in_events():
    lines = [
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "git status"}}
        ]}}),
        json.dumps({"type": "result"}),
    ]
    events = _drive_bridge_with(lines)
    tool_events = [e for e in events if e.kind == "tool_use"]
    assert len(tool_events) == 1
    assert tool_events[0].data["name"] == "Bash"


def test_tool_result_surfaces_in_events():
    lines = [
        json.dumps({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "abc", "content": "On branch main"}
        ]}}),
        json.dumps({"type": "result"}),
    ]
    events = _drive_bridge_with(lines)
    kinds = [e.kind for e in events]
    assert "tool_result" in kinds


def test_system_init_event_surfaces():
    lines = [
        json.dumps({"type": "system", "subtype": "init", "session_id": "abc"}),
        json.dumps({"type": "result"}),
    ]
    events = _drive_bridge_with(lines)
    kinds = [e.kind for e in events]
    assert "system" in kinds


def test_garbage_line_produces_error_event_but_does_not_crash():
    lines = [
        "this is not json",
        json.dumps({"type": "stream_event", "event": {"delta": {"type": "text_delta", "text": "નમસ્તે."}}}),
        json.dumps({"type": "result"}),
    ]
    events = _drive_bridge_with(lines)
    kinds = [e.kind for e in events]
    assert "error" in kinds
    assert "text_delta" in kinds


def test_code_blocks_in_text_delta_are_stripped():
    lines = [
        json.dumps({"type": "stream_event", "event": {"delta": {"type": "text_delta",
            "text": "પહેલાં. ```bash\ngit status\n``` બીજું."}}}),
        json.dumps({"type": "result"}),
    ]
    events = _drive_bridge_with(lines)
    spoken = [e.text for e in events if e.kind == "text_delta"]
    assert spoken == ["પહેલાં.", "બીજું."]


def test_turn_end_flushes_filter_pending():
    lines = [
        json.dumps({"type": "stream_event", "event": {"delta": {"type": "text_delta", "text": "no terminator here"}}}),
        json.dumps({"type": "result"}),
    ]
    events = _drive_bridge_with(lines)
    spoken = [e.text for e in events if e.kind == "text_delta"]
    assert spoken == ["no terminator here"]
