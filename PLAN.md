# GujaratiClaude — A Free, Open-Source Gujarati Voice Wrapper for Claude Code

## Context

**Problem.** Claude Code's built-in `/voice` mode only supports 20 languages — Gujarati is not one of them. A Gujarati-only speaker cannot meaningfully use Claude Code today.

**Insight.** Claude (the underlying model) already understands and produces Gujarati text fluently (~95%+ of English performance on standard benchmarks). The missing layer is purely **voice in / voice out in Gujarati**. We do not need to train any new models — high-quality open-source Gujarati STT/TTS already exist.

**Goal.** Build a small Windows desktop app that:
1. Sits idle listening for the wake word **"Claude"** (Alexa/Google-style)
2. Once woken, opens a small GUI window with a mic indicator
3. Records the user's Gujarati speech
4. Transcribes it to Gujarati text
5. Pipes the text to Claude Code running headlessly with full tool access
6. Streams Claude's Gujarati response back as natural Gujarati speech
7. Continues the conversation until the user closes it

**Outcome.** A Gujarati monolingual user can do anything Claude Code can do — edit files, run commands, search code, build projects — entirely by voice in their own language. Total monthly cost: $0 (only Anthropic API usage, which is already paid for Claude Code).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  GujaratiClaude.exe  (Python + Tkinter window)                       │
│                                                                       │
│   [ Idle ]  ──── wake word "Claude" detected ────► [ Listening ]    │
│      ▲                                                    │           │
│      │                                                    ▼           │
│      │   openWakeWord (custom "Claude" model)    sounddevice records │
│      │                                                    │           │
│      │                                                    ▼           │
│      │                                          faster-whisper        │
│      │                                          (Gujarati Whisper)    │
│      │                                                    │           │
│      │                                          Gujarati text         │
│      │                                                    ▼           │
│      │                                          subprocess.Popen      │
│      │                                          claude -p ...         │
│      │                                          --output-format       │
│      │                                            stream-json         │
│      │                                                    │           │
│      │                                          streaming Gujarati    │
│      │                                          tokens                │
│      │                                                    ▼           │
│      │                                          IndicF5 TTS engine    │
│      │                                          (sentence-by-sentence)│
│      │                                                    │           │
│      └────────── playback finishes ◄────── sounddevice plays         │
└─────────────────────────────────────────────────────────────────────┘
```

**Process model.** Single Python process with three async/threaded loops:
- `wake_loop` — continuously feeds audio to openWakeWord
- `dialog_loop` — once woken, drives record → STT → Claude → TTS → loop until silence
- `gui_loop` — Tkinter main loop, updates mic indicator + transcript view

---

## Open-Source Stack (everything MIT/Apache, $0/month)

| Layer | Library | Model | Why |
|---|---|---|---|
| Wake word | [openWakeWord](https://github.com/dscripka/openWakeWord) (Apache-2.0) | Custom-trained "Claude" model (~1hr via [their Colab notebook](https://github.com/dscripka/openWakeWord#training-new-models)) | Trains from 100% synthetic data, no recording needed |
| Audio I/O | `sounddevice` + `numpy` | — | Cross-platform, simple, Windows-friendly |
| Voice activity detection | Silero VAD (bundled with RealtimeSTT) | — | Detects when the user stops speaking so we don't have to push-to-talk |
| Gujarati STT | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT) | [`vasista22/whisper-gujarati-medium`](https://huggingface.co/vasista22/whisper-gujarati-medium) (Apache-2.0, 12.33% WER on FLEURS-gu) | Drops into faster-whisper unmodified, no NeMo/WSL2 needed, Windows-friendly. Falls back to vanilla `large-v3` if quality issues. |
| LLM + tools | Claude Code in headless mode | `claude -p "<prompt>" --output-format stream-json` | All Claude Code tools available; persistent session via `--continue`/`--resume` |
| Gujarati TTS | [AI4Bharat IndicF5](https://github.com/AI4Bharat/IndicF5) | Bundled checkpoint (Gujarati included) | Near-human quality, voice-clone style with reference clip |
| GUI | Tkinter (Python stdlib) | — | Zero extra deps, ships with Python; a single 400×300 window with mic indicator + Gujarati transcript |

**Skeleton to fork:** [`KoljaB/RealtimeVoiceChat`](https://github.com/KoljaB/RealtimeVoiceChat) (MIT) wires STT → LLM → TTS end-to-end with streaming. We replace its LLM call with a `claude -p` subprocess and swap its TTS engine for an IndicF5 adapter.

---

## Implementation Phases

### Phase 1 — Skeleton (Day 1)
1. Clone `KoljaB/RealtimeVoiceChat` as `C:\Users\test\GujaratiClaude\`
2. Run its `install.bat` to confirm baseline STT→LLM→TTS works in English
3. Strip out its browser UI; replace with a minimal Tkinter window (`gui.py`)

### Phase 2 — Gujarati STT (Day 1–2)
1. Configure RealtimeSTT to load `vasista22/whisper-gujarati-medium` via faster-whisper
2. Set language code to `gu`
3. Test with sample Gujarati phrases; verify transcription appears in Gujarati script (Unicode)
4. Tune VAD silence threshold for Gujarati prosody (default 0.5s usually works)

### Phase 3 — Claude Code subprocess glue (Day 2)
1. Write `claude_bridge.py` — wraps `subprocess.Popen(["claude", "-p", prompt, "--output-format", "stream-json", "--cwd", project_dir])` and parses streamed JSONL
2. Maintain session continuity via `--resume <session-id>` between turns
3. Add a system prompt prepended on first turn:
   ```
   તમે Claude Code છો. વપરાશકર્તા સાથે હંમેશા ગુજરાતીમાં વાત કરો.
   તમારી તમામ ફાઇલ ઓપરેશન્સ, શેલ કમાન્ડ્સ અને કોડ વિશ્લેષણ સામાન્ય રીતે કરો,
   પરંતુ માણસને બધા જવાબો ગુજરાતીમાં આપો.
   ```
   (= "You are Claude Code. Always speak Gujarati with the user. Do all file ops, shell commands, code analysis normally, but reply to the human only in Gujarati.")
4. Forward streamed assistant text to the TTS queue; ignore tool-use JSON events for speech (but show them in the GUI transcript)

### Phase 4 — Gujarati TTS (Day 3)
1. `pip install` IndicF5 deps in a Python 3.10 venv (Windows-supported)
2. Download the IndicF5 checkpoint + a Gujarati reference audio clip + transcript (provided in the repo's `prompts/` dir)
3. Write `indic_f5_engine.py` — an ~80-line subclass of RealtimeTTS's `BaseEngine` that calls IndicF5 sentence-by-sentence and yields PCM chunks
4. Plug it into RealtimeTTS's stream pipeline

### Phase 5 — Wake word "Claude" (Day 4)
1. Open [openWakeWord training Colab notebook](https://github.com/dscripka/openWakeWord)
2. Train a "Claude" model (about 1 hour, ~$0 on Colab free tier)
3. Save the resulting `.onnx` to `GujaratiClaude/models/claude_wakeword.onnx`
4. Add `wake_loop.py` — runs openWakeWord on a 16kHz audio stream, triggers `dialog_loop` on detection
5. After dialog ends (e.g., 10s silence or user says "બંધ કરો" / "stop"), return to wake-word listening

### Phase 6 — GUI polish (Day 5)
- Tkinter window with three states visually: **idle** (small grey dot), **listening** (pulsing red), **speaking** (green wave). Show last 5 exchanges of transcript in Gujarati. Always-on-top option. System tray icon via `pystray`.

### Phase 7 — Launcher (Day 5)
- `launch.bat` that activates the venv and runs `python main.py`
- Optional: Windows Task Scheduler entry to start on login

---

## Repository Structure

```
C:\Users\test\GujaratiClaude\
├── main.py                    # entrypoint: starts GUI + wake_loop
├── wake_loop.py               # openWakeWord listener
├── dialog_loop.py             # record → STT → Claude → TTS state machine
├── claude_bridge.py           # subprocess wrapper around `claude -p`
├── indic_f5_engine.py         # RealtimeTTS BaseEngine adapter for IndicF5
├── gui.py                     # Tkinter window
├── config.py                  # paths, model names, project_dir, system prompt
├── models/
│   ├── claude_wakeword.onnx   # custom-trained wake word
│   ├── whisper-gujarati/      # vasista22/whisper-gujarati-medium files
│   └── indic_f5/              # IndicF5 checkpoint + Gujarati reference clip
├── requirements.txt
├── install.bat
├── launch.bat
└── README.md
```

---

## Critical Files / Functions to Reference

- **RealtimeVoiceChat skeleton:** `KoljaB/RealtimeVoiceChat/server.py` — shows the STT→LLM→TTS plumbing we adapt
- **RealtimeSTT recorder API:** `KoljaB/RealtimeSTT/RealtimeSTT/audio_recorder.py` — `AudioToTextRecorder(wake_words=..., model='path/to/whisper-gujarati')`
- **RealtimeTTS engine interface:** `KoljaB/RealtimeTTS/RealtimeTTS/engines/base_engine.py` — subclass `BaseEngine`, implement `synthesize(text) -> Iterator[bytes]`
- **Claude Code headless docs:** [code.claude.com/docs/en/cli-reference](https://code.claude.com/docs/en/cli-reference) — `-p`, `--output-format stream-json`, `--resume`, `--cwd`
- **openWakeWord training:** [github.com/dscripka/openWakeWord/tree/main/notebooks](https://github.com/dscripka/openWakeWord) — `automatic_model_training.ipynb`
- **IndicF5 inference example:** [github.com/AI4Bharat/IndicF5/blob/main/inference.py](https://github.com/AI4Bharat/IndicF5)

---

## Verification Plan

End-to-end smoke test (Phase 1–4, no wake word yet):
1. Run `python main.py --project-dir C:\Users\test\WEE-Discount-Tracker`
2. Speak in Gujarati: *"WEE-Discount-Tracker ફોલ્ડરમાં કઈ ફાઇલો છે?"* (= "What files are in the WEE-Discount-Tracker folder?")
3. **Expect:** Whisper transcript appears in Gujarati. Claude responds in Gujarati listing the files (using its Glob tool internally). IndicF5 speaks the response.

Wake word test (after Phase 5):
4. Say "Claude" from across the room → mic indicator turns red within 1 second
5. Stay silent 10 seconds → returns to idle

Tool-use test:
6. Say *"એક નવી ફાઇલ બનાવો જેનું નામ test.txt હોય અને તેમાં 'નમસ્તે' લખો"* (= "Create a new file called test.txt with 'Hello' inside")
7. **Expect:** Claude uses Write tool, file appears on disk, Claude confirms in Gujarati

Bash test:
8. Say *"ગિટ સ્ટેટસ બતાવો"* (= "Show me git status")
9. **Expect:** Claude runs `git status`, summarizes output in Gujarati

Multi-turn context test:
10. Say *"હવે તે ફાઇલ ડિલીટ કરો"* (= "Now delete that file")
11. **Expect:** Claude remembers `test.txt` from turn 6 and deletes it — proves `--resume` session continuity works

---

## Known Gotchas

- **openWakeWord is English-only for training data.** Fine for "Claude" the brand name (pronounced the same in any language), but we can't easily train a Gujarati-word wake word. Acceptable.
- **IndicF5 license is not explicitly declared** in its README. For personal use this is fine; for commercial redistribution, verify with AI4Bharat first.
- **AI4Bharat IndicConformer (the more accurate STT alternative) needs NeMo, which is painful on native Windows** — use WSL2 if we ever switch from Whisper to IndicConformer.
- **First run downloads ~3 GB of model weights** (Whisper Gujarati + IndicF5). `install.bat` should cache these once.
- **Microphone permissions** on Windows 11: Settings → Privacy → Microphone must allow desktop apps. Add a startup check that fails loudly if denied.
- **Claude Code must already be authenticated** on this machine (`claude` CLI works in PowerShell). Verified — it does, since the user already runs Claude Code here.

---

## Future Enhancements (not in v1)

- Code-switching (Gujlish / Gujarati mixed with English technical terms) — Whisper handles this naturally; verify in testing
- "Push to talk" hotkey alternative for noisy environments
- Whisper streaming (partial transcripts) for snappier feel
- Replace Whisper with AI4Bharat IndicConformer under WSL2 for higher accuracy
- Package as a single `.exe` with PyInstaller for easier distribution to other Gujarati speakers
