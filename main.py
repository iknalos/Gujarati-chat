"""GujaratiClaude entrypoint.

Wires together:
- WakeLoop  → fires "wake" into the dialog loop
- DialogLoop → record → STT → Claude → TTS
- GujaratiClaudeGUI → Tk window showing state + transcript

Run on Windows from ``launch.bat`` (which activates the venv first).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import config


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="gujarati-claude")
    ap.add_argument("--project-dir", default=str(config.PROJECT_DIR),
                    help="Working directory for the Claude Code subprocess.")
    ap.add_argument("--no-wake", action="store_true",
                    help="Disable wake-word listener; trigger via GUI 'Wake' button.")
    ap.add_argument("--mock", action="store_true",
                    help="Run without heavy backends — useful for GUI smoke tests.")
    ap.add_argument("--text", action="store_true",
                    help="Keyboard input only — bypass mic/STT/TTS. Useful before "
                         "wake word / IndicF5 / Whisper are set up.")
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    if args.mock:
        return _run_mock()

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
    )
    dialog.add_state_listener(gui.push_state)
    dialog.add_transcript_listener(gui.push_transcript)
    dialog.start()

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
        if wake is not None:
            wake.stop()
        dialog.shutdown()
    return 0


def _run_text(args) -> int:
    """Keyboard-text mode: GUI + bridge, no audio. Lets a Gujarati speaker
    use Claude Code by typing, before audio is set up.
    """
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
        on_text_submit=driver.submit_text,
    )
    driver.add_state_listener(gui.push_state)
    driver.add_transcript_listener(gui.push_transcript)
    try:
        gui.run()
    finally:
        driver.shutdown()
    return 0


def _run_mock() -> int:
    """GUI-only mode for smoke-testing without audio/CUDA/Claude available.

    Wake button cycles through states and appends fake transcript entries
    so the visual UI can be verified end-to-end.
    """
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

    gui = GujaratiClaudeGUI(on_wake=fake_wake, on_stop=fake_stop, on_close=lambda: None)
    gui.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
