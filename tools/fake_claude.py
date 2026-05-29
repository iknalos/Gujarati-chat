"""A tiny fake of the ``claude -p --input-format stream-json`` subprocess.

Use this to verify the bridge → filter → TTS path on a box where you
don't have Claude Code authenticated yet, or to exercise the dialog
loop in CI.

Reads user-message JSON lines from stdin, echoes back stream_event
deltas in Gujarati so the filter has real characters to work with, then
emits a ``result`` event marking turn end.

Wire it in instead of the real binary:

    GC_CLAUDE_BIN=$(realpath tools/fake_claude.py) python tools/text_chat.py

(On Windows, set GC_CLAUDE_BIN=C:\path\to\python C:\...\fake_claude.py
or use ``py -3 tools/fake_claude.py`` via a tiny .cmd shim.)
"""
from __future__ import annotations

import json
import sys
import time


_REPLIES = [
    "નમસ્તે, હું તમારી વાત સાંભળી છું. તમે કહ્યું: ",
    "આ એક પરીક્ષણ પ્રતિક્રિયા છે. ",
    "વાસ્તવિક Claude Code અહીં વાસ્તવિક જવાબ આપશે.",
]


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _emit_init() -> None:
    _emit({"type": "system", "subtype": "init", "session_id": "fake-session-0001"})


def _handle_user_turn(user_text: str) -> None:
    # Stream the reply as small text_delta chunks so the bridge's filter
    # actually has to buffer across deltas — closest to real Claude output.
    full = _REPLIES[0] + user_text + ". " + _REPLIES[1] + _REPLIES[2]
    for i in range(0, len(full), 7):
        _emit({
            "type": "stream_event",
            "event": {"delta": {"type": "text_delta", "text": full[i:i + 7]}},
        })
        time.sleep(0.02)
    _emit({"type": "result", "session_id": "fake-session-0001"})


def main() -> int:
    _emit_init()
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _emit({"type": "system", "subtype": "error", "error": "bad json"})
            continue
        if msg.get("type") != "user":
            continue
        content = (msg.get("message") or {}).get("content") or []
        text = " ".join(b.get("text", "") for b in content if b.get("type") == "text")
        _handle_user_turn(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
