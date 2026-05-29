"""IndicF5 Gujarati TTS smoke test.

Synthesizes a fixed Gujarati phrase and plays it through the default
speakers. Verifies the reference clip + model + audio output path.

    python tools/tts_smoke.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config


def main() -> int:
    from indic_f5_engine import IndicF5Engine
    import sounddevice as sd
    import numpy as np

    engine = IndicF5Engine()
    text = "નમસ્તે, હું ગુજરાતી ક્લોડ છું. શું હું તમારી મદદ કરી શકું?"
    print(f"Synthesizing: {text}")
    t0 = time.monotonic()
    pcm_bytes = b"".join(engine.synthesize(text))
    elapsed = time.monotonic() - t0
    print(f"  synthesized {len(pcm_bytes)} bytes in {elapsed:.2f} s")

    audio = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32767.0
    sr = config.TTS_SAMPLE_RATE
    duration = len(audio) / sr
    rtf = elapsed / max(duration, 1e-6)
    print(f"  duration={duration:.2f}s realtime_factor={rtf:.2f} (lower is better)")
    if rtf > 1.0:
        print("  WARNING: synthesis slower than realtime; expect choppy dialog")

    print("Playing...")
    sd.play(audio, sr)
    sd.wait()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
