"""Verify install status. Prints a per-layer report; safe to re-run anytime.

    python tools/check_install.py

Exits 0 if at least text mode is usable, 1 otherwise. Voice-mode failures
are reported as warnings rather than errors so you can keep using text
mode while you sort the audio stack out.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config


GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def _ok(msg: str) -> None:   print(f"  {GREEN}✓{RESET} {msg}")
def _warn(msg: str) -> None: print(f"  {YELLOW}⚠{RESET} {msg}")
def _err(msg: str) -> None:  print(f"  {RED}✗{RESET} {msg}")


def check_python() -> bool:
    v = sys.version_info
    if v < (3, 10):
        _err(f"Python {v.major}.{v.minor}.{v.micro} — need 3.10+")
        return False
    _ok(f"Python {v.major}.{v.minor}.{v.micro}")
    return True


def check_tkinter() -> bool:
    try:
        import tkinter  # noqa
        _ok("tkinter available")
        return True
    except ImportError:
        _err("tkinter not installed (Windows: comes with python.org installers; Linux: apt install python3-tk)")
        return False


def check_claude() -> bool:
    if not shutil.which(config.CLAUDE_BIN):
        _err(f"`{config.CLAUDE_BIN}` not on PATH — install Claude Code from https://code.claude.com")
        return False
    try:
        r = subprocess.run([config.CLAUDE_BIN, "--version"], capture_output=True, timeout=10, text=True)
        _ok(f"`{config.CLAUDE_BIN}` found: {r.stdout.strip()}")
    except Exception as exc:
        _err(f"running `{config.CLAUDE_BIN} --version` failed: {exc}")
        return False
    try:
        r = subprocess.run([config.CLAUDE_BIN, "auth", "status"], capture_output=True, timeout=10)
        if r.returncode == 0:
            _ok("`claude auth status` — authenticated")
            return True
        else:
            _err("`claude auth status` exited non-zero — run `claude auth login`")
            return False
    except Exception as exc:
        _warn(f"`{config.CLAUDE_BIN} auth status` did not run: {exc}")
        return False


def check_voice_optional() -> int:
    """Return count of missing voice deps."""
    missing = 0
    for mod in ("numpy", "torch", "transformers", "RealtimeSTT", "RealtimeTTS",
                "sounddevice", "openwakeword", "onnxruntime", "huggingface_hub",
                "ctranslate2", "faster_whisper"):
        try:
            __import__(mod)
            _ok(f"voice dep '{mod}' importable")
        except ImportError:
            _warn(f"voice dep '{mod}' not installed (run install.bat for voice mode)")
            missing += 1
    return missing


def check_files() -> None:
    for p, label, fatal in [
        (config.GU_SYSTEM_PROMPT_FILE, "Gujarati system prompt", True),
        (config.WHISPER_CT2_DIR, "Whisper-CT2 model dir", False),
        (config.INDIC_F5_DIR, "IndicF5 weights dir", False),
        (config.WAKEWORD_ONNX, "Trained 'Claude' wake-word ONNX", False),
        (config.GU_REFERENCE_WAV, "Gujarati reference audio (.wav)", False),
    ]:
        if p.exists():
            _ok(f"{label} present: {p}")
        elif fatal:
            _err(f"missing {label}: {p}")
        else:
            _warn(f"missing {label} (optional, voice mode only): {p}")


def check_gpu() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            _ok(f"CUDA available: {torch.cuda.get_device_name(0)} ({torch.cuda.get_device_properties(0).total_memory // 1024**3} GB)")
        else:
            _warn("CUDA not available — IndicF5 will run on CPU (3-5x realtime, not usable conversationally)")
    except ImportError:
        _warn("torch not installed yet — install.bat will add CUDA PyTorch")


def main() -> int:
    print(f"\n{DIM}=== Core (text mode) ==={RESET}")
    core_ok = check_python() & check_tkinter() & check_claude()

    print(f"\n{DIM}=== Files ==={RESET}")
    check_files()

    print(f"\n{DIM}=== Voice mode (optional) ==={RESET}")
    missing = check_voice_optional()

    print(f"\n{DIM}=== GPU ==={RESET}")
    check_gpu()

    print()
    if core_ok:
        print(f"{GREEN}Text mode is ready.{RESET}  Run:  python main.py --text")
        if missing:
            print(f"{YELLOW}Voice mode needs install.bat (and an NVIDIA GPU).{RESET}")
        else:
            print(f"{GREEN}Voice mode deps are installed.{RESET}  Run:  launch.bat")
        return 0
    else:
        print(f"{RED}Core prerequisites missing — fix the errors above.{RESET}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
