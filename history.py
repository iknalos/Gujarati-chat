"""Conversation history persistence — visual transcript + Claude session id.

On every shutdown we save the last N transcript entries plus the Claude
``session_id`` we observed from the bridge. On next launch we replay those
entries into the GUI and pass the session id to ``claude -p --resume`` so
the model has full multi-turn context, not just visual.

Storage: a single JSON file in the user's home folder (cross-launch, not
per-repo, since users typically run one dashboard at a time).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


HISTORY_FILE = Path.home() / ".gujarati_claude_history.json"
MAX_TRANSCRIPT_ENTRIES = 100


@dataclass
class TranscriptEntry:
    role: str
    text: str
    ts: str = ""


@dataclass
class History:
    session_id: Optional[str] = None
    project_dir: Optional[str] = None
    transcript: list[TranscriptEntry] = field(default_factory=list)

    def append(self, role: str, text: str) -> None:
        self.transcript.append(TranscriptEntry(
            role=role, text=text,
            ts=datetime.now().isoformat(timespec="seconds"),
        ))


def load() -> History:
    """Load history from disk. Returns empty History if file is missing or
    malformed — never raises (corrupt history must not block app startup)."""
    if not HISTORY_FILE.exists():
        return History()
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return History(
            session_id=data.get("session_id"),
            project_dir=data.get("project_dir"),
            transcript=[TranscriptEntry(**e) for e in data.get("transcript", [])],
        )
    except (json.JSONDecodeError, TypeError, KeyError):
        return History()


def save(history: History) -> None:
    """Best-effort save. Failures are swallowed (we'd rather lose history
    than crash the app on close)."""
    capped = history.transcript[-MAX_TRANSCRIPT_ENTRIES:]
    data = {
        "session_id": history.session_id,
        "project_dir": history.project_dir,
        "transcript": [asdict(e) for e in capped],
    }
    try:
        HISTORY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def clear() -> None:
    """Wipe persisted history (used by Clear quick-action if we wire it)."""
    try:
        HISTORY_FILE.unlink()
    except FileNotFoundError:
        pass
