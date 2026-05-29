# GujaratiClaude

A Windows desktop wrapper that lets a Gujarati-only speaker use the full
power of Claude Code by voice. Idle on the wake word **"Claude"**, then:

```
mic → openWakeWord → faster-whisper (Gujarati) → claude -p (stream-json) → IndicF5 → speakers
```

100% open-source (MIT/Apache). $0/month beyond the Claude usage you're
already paying for.

See [`PLAN.md`](PLAN.md) for the full design discussion, library
verification, and known gotchas.

---

## Quickstart

### Prerequisites
- Windows 10/11
- Python 3.10 (3.11 also tested; 3.12 may need package adjustments)
- [Claude Code](https://code.claude.com) authenticated (`claude auth status` exits 0)
- **NVIDIA GPU with ≥6 GB VRAM** for realtime TTS (CPU is 3-5× realtime — unusable for conversation)
- ~5 GB free disk for model weights

### Install
```cmd
git clone https://github.com/iknalos/GujaratiClaude.git
cd GujaratiClaude
install.bat
```

`install.bat` creates a venv, installs PyTorch (CUDA 12.1) + onnxruntime
+ project deps, converts the Gujarati Whisper model to CTranslate2 format,
and downloads the IndicF5 weights. Two manual steps remain at the end:

1. **Train a wake word.** Open the [openWakeWord training Colab](https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb), train "Claude" (~1 hr free tier), save the resulting `.onnx` to `models\claude_wakeword.onnx`. Until you do, launch with `--no-wake` and click the GUI "Wake" button.
2. **Add a reference voice.** Drop a clean 5-10 second Gujarati audio clip at `prompts\gu_reference.wav` and its transcript at `prompts\gu_reference.txt`. IndicF5 clones this clip's voice.

### Run
```cmd
launch.bat
```

The window stays always-on-top with a state indicator and transcript pane.
Say "Claude" to start a conversation; say "બંધ કરો" (= "stop") or stay
silent for 12 s to end it.

---

## Verifying each piece independently

If something doesn't work end-to-end, isolate the layer:

| What to test | Command | Expected |
|---|---|---|
| Claude bridge (no audio) | `python tools\text_chat.py` | Type Gujarati, see streaming Gujarati response |
| Whisper STT | `python tools\stt_smoke.py` | Speak 5 phrases, see Gujarati Unicode transcripts |
| IndicF5 TTS | `python tools\tts_smoke.py` | Hear a spoken Gujarati sentence; realtime factor < 1.0 |
| Text-mode GUI (no audio) | `launch.bat --text` | Window opens, type Gujarati, see streaming Gujarati reply |
| GUI (no backends at all) | `python main.py --mock` | Window opens; Wake button cycles state colors |
| Pure-Python logic | `python -m pytest tests/` | 21 tests pass |

---

## Configuration

Override any value in `config.py` with a `GC_<NAME>` environment variable. The most useful:

| Variable | Default | What it does |
|---|---|---|
| `GC_CLAUDE_BIN` | `claude` | Path to the `claude` executable |
| `GC_PROJECT_DIR` | repo root | Working directory passed to the subprocess |
| `GC_PERMISSION_MODE` | `acceptEdits` | `acceptEdits` / `auto` / `default` / `bypassPermissions` |
| `GC_STT_COMPUTE_TYPE` | `int8_float16` | `int8` (CPU), `float16` (GPU), `int8_float16` (GPU mixed) |
| `GC_WAKE_THRESHOLD` | `0.5` | Increase if you get false wakes |
| `GC_DIALOG_TIMEOUT_SECS` | `12` | Silence before returning to wake-word listening |

---

## Architecture

See [`PLAN.md`](PLAN.md) for the full diagram. In short: a single Python
process runs four threads — wake-word listener, dialog state machine,
Claude subprocess reader, and the Tk mainloop — all communicating
through thread-safe queues. The `claude -p` subprocess is **persistent**
(stays alive for the lifetime of the app, multi-turn via stream-json
stdin), so each turn is just a JSON write — no cold start, no `--resume`
gymnastics.

---

## Repo layout

```
GujaratiClaude/
├── main.py                    entrypoint
├── gui.py                     Tkinter window, three states, transcript
├── dialog_loop.py             record → STT → Claude → TTS state machine
├── claude_bridge.py           persistent stream-json subprocess
├── response_filter.py         strip code, buffer sentences for TTS
├── wake_loop.py               openWakeWord listener
├── indic_f5_engine.py         RealtimeTTS-shaped IndicF5 adapter
├── config.py                  centralized settings (env-overridable)
├── prompts/
│   ├── gu_system.txt          Gujarati persona prompt for Claude
│   ├── gu_reference.wav       (you provide) reference voice for cloning
│   └── gu_reference.txt       (you provide) transcript of the above
├── models/                    (populated by install.bat)
├── tools/
│   ├── text_chat.py           Phase-3 smoke: type → Claude → print
│   ├── stt_smoke.py           Phase-2 smoke: mic → Whisper → print
│   └── tts_smoke.py           Phase-4 smoke: text → IndicF5 → speakers
├── tests/                     21 unit tests for filter + bridge protocol
├── install.bat
├── launch.bat
└── PLAN.md
```

---

## Status

| Phase | What | Status |
|---|---|---|
| 1 | Skeleton + config + structure | ✅ done |
| 2 | Gujarati STT (Whisper-CT2) | ⚠ requires Windows + mic to verify |
| 3 | Claude Code bridge | ✅ logic done + 21 tests; needs `claude` auth to E2E |
| 4 | IndicF5 TTS adapter | ⚠ requires CUDA + weights to verify |
| 5 | Wake word | ⚠ requires trained ONNX (1 hr Colab) |
| 6 | GUI polish | ✅ done (headless-smoked with Xvfb) |
| 7 | Launcher / packaging | ✅ install.bat, launch.bat |

---

## License

MIT. See library licenses in `PLAN.md` for the upstream stack.
