"""Make sure the bridge surfaces failures instead of hanging.

When the ``claude`` subprocess dies (auth expired, segfault, user killed
it), readers waiting on ``events()`` would otherwise block forever.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from queue import Empty

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_bridge import ClaudeBridge


def test_send_after_subprocess_dies_raises_broken_pipe(tmp_path):
    """Use /bin/true as the 'claude' binary — exits immediately."""
    b = ClaudeBridge(
        project_dir=tmp_path,
        system_prompt_file=tmp_path / "fake.txt",
        claude_bin="/bin/true",
    )
    (tmp_path / "fake.txt").write_text("")
    b.start()
    # Give /bin/true a moment to exit
    time.sleep(0.2)
    try:
        try:
            b.send("hello")
        except BrokenPipeError:
            return  # expected
        # If send didn't raise, we should at least see error events on the queue.
        events = []
        while True:
            try:
                events.append(b.events().get_nowait())
            except Empty:
                break
        kinds = [e.kind for e in events]
        assert "error" in kinds or "turn_end" in kinds
    finally:
        b.close()


def test_subprocess_exit_emits_error_and_turn_end(tmp_path):
    """When stdout closes (process exit), reader must emit error + turn_end
    so any waiter unblocks rather than hanging."""
    b = ClaudeBridge(
        project_dir=tmp_path,
        system_prompt_file=tmp_path / "fake.txt",
        claude_bin="/bin/true",
    )
    (tmp_path / "fake.txt").write_text("")
    b.start()
    # The reader thread should drain (empty) stdout and emit our two events.
    deadline = time.monotonic() + 3
    events = []
    while time.monotonic() < deadline:
        try:
            events.append(b.events().get(timeout=0.2))
        except Empty:
            if events:
                break
            continue
    b.close()
    kinds = [e.kind for e in events]
    assert "error" in kinds
    assert "turn_end" in kinds
