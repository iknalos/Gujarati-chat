"""Background polling thread that watches the outputs/ directory and calls
a callback when a new file appears.

Polling at 1 Hz keeps the dependency surface zero (no watchdog/inotify).
The outputs/ folder shouldn't change frequently enough for that to matter.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional


class OutputsWatcher:
    def __init__(
        self,
        outputs_dir: Path,
        on_new_file: Callable[[Path], None],
        poll_interval_sec: float = 1.0,
    ) -> None:
        self.outputs_dir = outputs_dir
        self.on_new_file = on_new_file
        self.poll_interval = poll_interval_sec
        self._stop = threading.Event()
        self._known: set[Path] = set()
        self._mtimes: dict[Path, float] = {}
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        # Seed known set on startup so existing files don't fire "new file" events.
        # Existing files are still browsable via the file list — the watcher
        # only emits on changes from this point forward.
        self._known, self._mtimes = self._scan()
        self._thread = threading.Thread(
            target=self._loop, name="outputs-watcher", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def initial_files(self) -> list[Path]:
        """Files already present when start() ran — caller can show them too."""
        return sorted(self._known, key=lambda p: self._mtimes.get(p, 0.0))

    def _loop(self) -> None:
        while not self._stop.wait(self.poll_interval):
            current, current_mtimes = self._scan()
            new_files = current - self._known
            changed = {
                p for p in current & self._known
                if current_mtimes.get(p) != self._mtimes.get(p)
            }
            for path in new_files | changed:
                try:
                    self.on_new_file(path)
                except Exception:
                    pass
            self._known = current
            self._mtimes = current_mtimes

    def _scan(self) -> tuple[set[Path], dict[Path, float]]:
        if not self.outputs_dir.exists():
            return set(), {}
        out: set[Path] = set()
        mt: dict[Path, float] = {}
        try:
            for p in self.outputs_dir.iterdir():
                if p.is_file():
                    rp = p.resolve()
                    out.add(rp)
                    try:
                        mt[rp] = rp.stat().st_mtime
                    except OSError:
                        pass
        except OSError:
            pass
        return out, mt
