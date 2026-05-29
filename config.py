"""Central configuration for GujaratiClaude.

All paths are relative to the repo root unless absolute. Override any value
by setting the matching ``GC_<NAME>`` environment variable before launch.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def _env(name: str, default: str) -> str:
    return os.environ.get(f"GC_{name}", default)


# --- Paths -------------------------------------------------------------------
PROMPTS_DIR = REPO_ROOT / "prompts"
MODELS_DIR = REPO_ROOT / "models"

GU_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "gu_system.txt"
GU_REFERENCE_WAV = PROMPTS_DIR / "gu_reference.wav"
GU_REFERENCE_TXT = PROMPTS_DIR / "gu_reference.txt"

WHISPER_CT2_DIR = MODELS_DIR / "whisper-gujarati-ct2"
INDIC_F5_DIR = MODELS_DIR / "indic_f5"
WAKEWORD_ONNX = MODELS_DIR / "claude_wakeword.onnx"


# --- Claude Code subprocess --------------------------------------------------
CLAUDE_BIN = _env("CLAUDE_BIN", "claude")
PROJECT_DIR = Path(_env("PROJECT_DIR", str(REPO_ROOT))).resolve()
PERMISSION_MODE = _env("PERMISSION_MODE", "acceptEdits")


# --- STT ---------------------------------------------------------------------
STT_LANGUAGE = "gu"
STT_COMPUTE_TYPE = _env("STT_COMPUTE_TYPE", "int8_float16")
STT_SILENCE_SECS = float(_env("STT_SILENCE_SECS", "0.6"))
STT_SILERO_SENSITIVITY = float(_env("STT_SILERO_SENSITIVITY", "0.4"))


# --- TTS ---------------------------------------------------------------------
TTS_SAMPLE_RATE = 24000


# --- Wake word ---------------------------------------------------------------
WAKE_THRESHOLD = float(_env("WAKE_THRESHOLD", "0.5"))
DIALOG_TIMEOUT_SECS = float(_env("DIALOG_TIMEOUT_SECS", "12"))
STOP_PHRASE = "બંધ કરો"


# --- Audio -------------------------------------------------------------------
MIC_SAMPLE_RATE = 16000
MIC_CHANNELS = 1
