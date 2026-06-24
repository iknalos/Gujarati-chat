"""GujaratiClaude entrypoint.

Wires together:
- WakeLoop  → fires "wake" into the dialog loop (voice mode)
- DialogLoop → record → STT → Claude → TTS (voice mode)
- TextModeDriver → keyboard → Claude → text (text mode)
- GujaratiClaudeGUI → unified Tk dashboard (chat left, outputs right)
- OutputsWatcher → polls outputs/ folder and pushes new files to the panel

Run on Windows from ``launch.bat`` (which activates the venv first).
"""
from __future__ import annotations

import argparse
import faulthandler
import os
import sys
from pathlib import Path

import config

# When launched windowless (pythonw.exe from a desktop shortcut / .lnk) there
# is no console attached, so sys.stdout and sys.stderr are None. Any print() —
# or faulthandler.enable() below — then raises and the process dies silently
# before the window ever appears. Route them to the null device so the app
# always launches cleanly from an icon. (Running from a terminal is unaffected:
# stdout/stderr are real there and left alone.)
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

# Dump tracebacks for native crashes (sv_ttk theme, tkinterweb, PIL, etc.)
# straight to stderr — otherwise a segfault gives the user a window that
# silently disappears.
faulthandler.enable()


def _preflight(claude_bin: str) -> None:
    """Print friendly messages for the most common setup failures. Doesn't
    abort — we want the user to see them all rather than fixing one at a
    time."""
    import shutil
    import subprocess
    # On Windows the CLI is a `claude.cmd` shim; subprocess won't resolve the
    # bare name, so use the full path shutil.which() gives us — otherwise the
    # call below raises WinError 2 and prints a bogus "could not run" warning.
    resolved = shutil.which(claude_bin)
    if not resolved:
        print(
            f"⚠  Cannot find '{claude_bin}' on PATH. Install Claude Code "
            f"from https://code.claude.com and ensure it's in PATH.",
            file=sys.stderr,
        )
        return
    try:
        r = subprocess.run(
            [resolved, "auth", "status"], capture_output=True, timeout=10
        )
        if r.returncode != 0:
            print(
                "⚠  `claude auth status` exited non-zero. Run `claude auth login` "
                "before launching GujaratiClaude.",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"⚠  Could not run `{claude_bin} auth status`: {exc}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="gujarati-claude")
    ap.add_argument("--project-dir", default=str(config.PROJECT_DIR),
                    help="Working directory for the Claude Code subprocess.")
    ap.add_argument("--no-wake", action="store_true",
                    help="Disable wake-word listener; trigger via GUI 'Wake' button.")
    ap.add_argument("--mock", action="store_true",
                    help="Run without heavy backends — useful for GUI smoke tests.")
    ap.add_argument("--text", action="store_true",
                    help="Tkinter keyboard-only mode (legacy). Bypass mic/STT/TTS.")
    ap.add_argument("--web", action="store_true",
                    help="Launch the local webapp (FastAPI + pywebview) — the new default UI.")
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    if args.mock:
        return _run_mock()

    _preflight(config.CLAUDE_BIN)

    if args.web:
        return _run_web(args)

    if args.text:
        return _run_text(args)

    from dialog_loop import DialogLoop
    from gui import GujaratiClaudeGUI
    from wake_loop import WakeLoop

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"--project-dir {project_dir} is not a directory", file=sys.stderr)
        return 2

    dialog = DialogLoop(project_dir=project_dir)
    gui = GujaratiClaudeGUI(
        on_wake=dialog.wake,
        on_stop=dialog.stop_dialog,
        on_close=dialog.shutdown,
        outputs_dir=config.OUTPUTS_DIR,
    )
    dialog.add_state_listener(gui.push_state)
    dialog.add_transcript_listener(gui.push_transcript)
    dialog.start()

    watcher = _start_watcher(gui)

    wake = None
    if not args.no_wake and config.WAKEWORD_ONNX.exists():
        wake = WakeLoop(model_path=config.WAKEWORD_ONNX, on_wake=dialog.wake)
        wake.start()
    elif not args.no_wake:
        print(
            f"Wake-word model not found at {config.WAKEWORD_ONNX}; "
            f"falling back to the GUI 'Wake' button.",
            file=sys.stderr,
        )

    try:
        gui.run()
    finally:
        watcher.stop()
        if wake is not None:
            wake.stop()
        dialog.shutdown()
    return 0


def _run_web(args) -> int:
    """Launch the webapp: FastAPI server on localhost + pywebview window."""
    from webapp.webapp_main import run as run_web

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"--project-dir {project_dir} is not a directory", file=sys.stderr)
        return 2
    return run_web(project_dir=project_dir)


def _run_text(args) -> int:
    """Keyboard-text mode: GUI + bridge, no audio."""
    from gui import GujaratiClaudeGUI
    from text_mode import TextModeDriver

    project_dir = Path(args.project_dir).resolve()
    if not project_dir.is_dir():
        print(f"--project-dir {project_dir} is not a directory", file=sys.stderr)
        return 2

    driver = TextModeDriver(project_dir=project_dir)
    gui = GujaratiClaudeGUI(
        on_wake=lambda: None,
        on_stop=lambda: None,
        on_close=driver.shutdown,
        outputs_dir=config.OUTPUTS_DIR,
        on_text_submit=driver.submit_text,
        on_clear=driver.clear_history,
    )
    driver.add_state_listener(gui.push_state)
    driver.add_transcript_listener(gui.push_transcript)

    # Replay any persisted transcript into the GUI; Claude's own memory is
    # restored by the bridge passing --resume <session_id>.
    driver.replay_history()

    watcher = _start_watcher(gui)

    try:
        gui.run()
    finally:
        watcher.stop()
        driver.shutdown()
    return 0


def _start_watcher(gui):
    """Start the OutputsWatcher pointed at the GUI's embedded outputs panel.

    Failure in the watcher must not break the chat: any exception is logged
    and a no-op watcher is returned in its place.
    """
    from outputs_watcher import OutputsWatcher
    try:
        config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        watcher = OutputsWatcher(config.OUTPUTS_DIR, gui.outputs_panel.push_file)
        watcher.start()
        gui.outputs_panel.seed_existing(watcher.initial_files())
        return watcher
    except Exception as exc:
        print(f"⚠  Outputs watcher disabled: {exc}", file=sys.stderr)
        class _NullWatcher:
            def stop(self): pass
        return _NullWatcher()


def _run_mock() -> int:
    """GUI-only mode for smoke-testing without audio/CUDA/Claude available."""
    from gui import GujaratiClaudeGUI
    from dialog_loop import DialogTranscriptEntry

    state_cycle = ["listening", "thinking", "speaking", "idle"]
    idx = {"i": 0}

    def fake_wake():
        idx["i"] = (idx["i"] + 1) % len(state_cycle)
        gui.push_state(state_cycle[idx["i"]])
        gui.push_transcript(DialogTranscriptEntry(role="user", text="આ એક પરીક્ષણ વાક્ય છે."))
        gui.push_transcript(DialogTranscriptEntry(role="assistant", text="હા, હું તમારી વાત સાંભળું છું."))

    def fake_stop():
        gui.push_state("idle")

    config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    gui = GujaratiClaudeGUI(
        on_wake=fake_wake, on_stop=fake_stop, on_close=lambda: None,
        outputs_dir=config.OUTPUTS_DIR,
    )
    gui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
