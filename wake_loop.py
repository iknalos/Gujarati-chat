"""Wake-word listener that posts a WAKE event when "Claude" is detected.

Streams 16 kHz mono audio frames from the default mic through openWakeWord
using only ``onnxruntime`` (Windows has no tflite-runtime wheels). On a
positive detection above ``threshold`` we call the supplied callback once,
then suppress further detections for ``cooldown_secs`` so a single
utterance doesn't fire twice.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

import numpy as np

import config


class WakeLoop:
    def __init__(
        self,
        model_path: Path,
        on_wake: Callable[[], None],
        threshold: float = None,
        cooldown_secs: float = 2.0,
    ) -> None:
        self._model_path = Path(model_path)
        self._on_wake = on_wake
        self._threshold = threshold if threshold is not None else config.WAKE_THRESHOLD
        self._cooldown = cooldown_secs
        self._stop = threading.Event()
        self._thread = None  # type: ignore[assignment]
        self._last_fire = 0.0

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="wake-loop", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        # Lazy imports so unit tests don't need the audio stack installed.
        import sounddevice as sd
        from openwakeword.model import Model

        oww = Model(
            wakeword_models=[str(self._model_path)],
            inference_framework="onnx",  # Windows-only, no tflite
        )
        frame_samples = 1280  # 80 ms @ 16 kHz, openWakeWord's expected frame

        def callback(indata, frames, time_info, status):
            if status:
                # Drop the frame on overflow; better than backpressure on the mic.
                return
            mono = (indata[:, 0] * 32767).astype(np.int16)
            predictions = oww.predict(mono)
            for score in predictions.values():
                if score < self._threshold:
                    continue
                now = time.monotonic()
                if now - self._last_fire < self._cooldown:
                    continue
                self._last_fire = now
                self._on_wake()
                return

        with sd.InputStream(
            samplerate=config.MIC_SAMPLE_RATE,
            channels=config.MIC_CHANNELS,
            dtype="float32",
            blocksize=frame_samples,
            callback=callback,
        ):
            while not self._stop.is_set():
                self._stop.wait(timeout=0.1)
