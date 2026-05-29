"""Microphone → Whisper Gujarati transcript smoke test.

Run after Phase-2 install. Speak 5 Gujarati phrases; each one should print
as Gujarati Unicode. No Claude, no TTS, no wake word.

    python tools/stt_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config


def main() -> int:
    from RealtimeSTT import AudioToTextRecorder

    recorder = AudioToTextRecorder(
        model=str(config.WHISPER_CT2_DIR),
        language=config.STT_LANGUAGE,
        compute_type=config.STT_COMPUTE_TYPE,
        silero_sensitivity=config.STT_SILERO_SENSITIVITY,
        post_speech_silence_duration=config.STT_SILENCE_SECS,
        spinner=False,
        use_microphone=True,
    )
    print("Speak 5 Gujarati phrases. Pause between each. Ctrl-C to exit.")
    try:
        for i in range(5):
            print(f"\n[{i+1}/5] speak now...")
            text = recorder.text()
            print(f"  → {text!r}")
    finally:
        recorder.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
