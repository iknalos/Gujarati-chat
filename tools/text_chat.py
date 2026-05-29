"""Headless text chat against the persistent Claude Code bridge.

Use this to verify the Phase-3 plumbing on any machine where ``claude`` is
authenticated, without any audio dependencies. You type Gujarati (or
English), and you see Claude's streaming response printed sentence by
sentence — same path the TTS will consume.

    python tools/text_chat.py --project-dir .

Type "quit" or Ctrl-D to exit.
"""
from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path
from queue import Empty

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from claude_bridge import ClaudeBridge, StreamEvent


def _drain(bridge: ClaudeBridge, idle_after_turn_end: bool = True) -> None:
    """Drain events from the bridge until we see a turn_end (or 30 s idle)."""
    q = bridge.events()
    while True:
        try:
            ev: StreamEvent = q.get(timeout=30)
        except Empty:
            print("\n[no response for 30 s]", file=sys.stderr)
            return
        if ev.kind == "text_delta":
            print(f"  → {ev.text}")
        elif ev.kind == "tool_use":
            d = ev.data or {}
            print(f"  [tool: {d.get('name')} {d.get('input')}]", file=sys.stderr)
        elif ev.kind == "tool_result":
            d = ev.data or {}
            content = d.get("content")
            preview = (content if isinstance(content, str) else str(content))[:120]
            print(f"  [result: {preview}]", file=sys.stderr)
        elif ev.kind == "system":
            d = ev.data or {}
            sub = d.get("subtype", "")
            if sub == "api_retry":
                print(f"  [retry attempt {d.get('attempt')}: {d.get('error')}]", file=sys.stderr)
        elif ev.kind == "error":
            d = ev.data or {}
            print(f"  [bridge error: {d.get('message')}]", file=sys.stderr)
        elif ev.kind == "turn_end":
            return


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", default=str(config.PROJECT_DIR))
    ap.add_argument("--claude-bin", default=config.CLAUDE_BIN)
    ap.add_argument("--permission-mode", default=config.PERMISSION_MODE)
    args = ap.parse_args()

    bridge = ClaudeBridge(
        project_dir=Path(args.project_dir).resolve(),
        system_prompt_file=config.GU_SYSTEM_PROMPT_FILE,
        claude_bin=args.claude_bin,
        permission_mode=args.permission_mode,
    )
    bridge.start()
    try:
        while True:
            try:
                line = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if line.lower() in {"quit", "exit"}:
                break
            bridge.send(line)
            _drain(bridge)
    finally:
        bridge.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
