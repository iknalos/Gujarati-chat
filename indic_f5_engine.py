"""IndicF5 adapter for the RealtimeTTS streaming pipeline.

IndicF5 is loaded once at construction with a fixed Gujarati reference clip
and its transcript. ``synthesize(text)`` then voice-clones the reference's
style onto ``text``.

Sample-rate note: IndicF5 emits 24 kHz mono float32 audio. RealtimeTTS wants
16-bit PCM bytes; we convert in ``_to_pcm16``.

Hardware: a CUDA GPU is required for realtime — see ``config.py`` and the
README. On CPU you will see roughly 3-5× realtime, which makes the app
unusable as a conversational interface.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Iterator, Optional

import numpy as np

import config

# These heavy deps are imported lazily so the module is importable on
# machines without torch/transformers (e.g., a CI box running the unit tests).


class IndicF5Engine:
    """Drop-in replacement for a RealtimeTTS BaseEngine.

    Implements the three method names the RealtimeTTS stream pipeline
    actually calls: ``get_stream_info()``, ``synthesize(text)``, and
    ``shutdown()``. (RealtimeTTS exposes a richer ``BaseEngine`` class but
    these are the only members the engine-selection path uses for a
    custom engine.)
    """

    def __init__(
        self,
        repo_id: str = "ai4bharat/IndicF5",
        ref_audio_path: Optional[Path] = None,
        ref_text: Optional[str] = None,
        device: str = "cuda",
    ) -> None:
        import torch
        from transformers import AutoModel

        self.device = device if torch.cuda.is_available() else "cpu"
        if self.device != "cuda":
            print(
                "WARNING: IndicF5 running on CPU. Expect 3-5x realtime; "
                "the conversational loop will not feel responsive.",
                flush=True,
            )
        # AutoModel returns an instance of the F5 model wrapper exposed by
        # AI4Bharat's repo; ``trust_remote_code=True`` is required.
        self._model = AutoModel.from_pretrained(repo_id, trust_remote_code=True)
        self._model = self._model.to(self.device)
        self._ref_audio_path = str(ref_audio_path or config.GU_REFERENCE_WAV)
        if ref_text is not None:
            self._ref_text = ref_text
        else:
            self._ref_text = Path(config.GU_REFERENCE_TXT).read_text(encoding="utf-8").strip()
        self._sample_rate = config.TTS_SAMPLE_RATE
        self._warmup()

    # ---- RealtimeTTS-style hooks ------------------------------------------

    def get_stream_info(self):
        # (pyaudio_format_id_for_paInt16, channels, sample_rate)
        return 8, 1, self._sample_rate  # 8 == paInt16 in PyAudio

    def synthesize(self, text: str) -> Iterator[bytes]:
        if not text or not text.strip():
            return iter(())
        audio = self._model(
            text,
            ref_audio_path=self._ref_audio_path,
            ref_text=self._ref_text,
        )
        pcm = self._to_pcm16(audio)
        yield pcm

    def shutdown(self) -> None:
        # No persistent resources beyond the model itself; torch handles GC.
        self._model = None

    # ---- Internals --------------------------------------------------------

    def _warmup(self) -> None:
        """One short synth so the first user-visible utterance doesn't pay
        the JIT/import cost."""
        try:
            list(self.synthesize("નમસ્તે."))
        except Exception:
            # Warm-up is best-effort; don't crash startup on transient errors.
            pass

    @staticmethod
    def _to_pcm16(audio) -> bytes:
        if hasattr(audio, "cpu"):
            audio = audio.cpu().numpy()
        arr = np.asarray(audio, dtype=np.float32)
        # Some IndicF5 builds return a (1, N) tensor; squeeze it.
        arr = np.squeeze(arr)
        # Normalize/clip then scale to int16.
        peak = float(np.max(np.abs(arr))) or 1.0
        if peak > 1.0:
            arr = arr / peak
        arr = np.clip(arr, -1.0, 1.0)
        return (arr * 32767).astype(np.int16).tobytes()
