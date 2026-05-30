# GujaratiClaude

A Windows desktop wrapper that lets a Gujarati-only speaker use the full
power of [Claude Code](https://code.claude.com) — by keyboard today, by
voice when you wire that up. Same brain as the official Claude Code CLI;
all of its tools (Read, Write, Edit, Bash, Glob, Grep) are available; the
GUI just speaks Gujarati on both sides.

```
┌─ GujaratiClaude ────────────────────────────────────────────────────┐
│ ● idle       GujaratiClaude                       [Wake]  [Stop]    │
├──────────────────────────────────┬──────────────────────────────────┤
│  તમે: એક chart બનાવો               │ 📂 outputs/                       │
│  Claude: chart.png બની ગયું        │  🖼  monthly_financials.png  112KB │
│  ...                             │  🖼  smoke_test.png            36KB │
│                                  │  [Open] [Folder] [Refresh]        │
│  (chat scrolls)                  │  ┌──────────────────────────┐    │
│                                  │  │  [chart preview]          │    │
│                                  │  └──────────────────────────┘    │
├──────────────────────────────────┴──────────────────────────────────┤
│ [type Gujarati...                                          ] [મોકલો] │
└─────────────────────────────────────────────────────────────────────┘
```

**What works today** (text mode):
- Chat with Claude in Gujarati — full Claude Code tool access
- Claude can create matplotlib charts, process Excel, write files; they
  auto-appear in the right pane with inline preview
- Claude can scaffold React/Next.js projects, run dev servers, push to
  GitHub, deploy to Vercel — all from a Gujarati prompt
- All open-source, MIT/Apache, $0/month beyond your Claude API usage

**Coming when wired:** voice in/voice out (Whisper STT → IndicF5 TTS →
openWakeWord "Claude" wake word) — see [Voice mode](#voice-mode-optional)
for the remaining work.

---

## Fresh-machine setup (text mode, ~10 minutes)

### Prerequisites — install these once

| Tool | Why | Where |
|---|---|---|
| **Miniconda** | Python 3.11 env (`gc311`) for matplotlib/pandas/etc. | https://docs.conda.io/en/latest/miniconda.html |
| **Claude Code CLI** | The brain. Must be authenticated. | https://code.claude.com — then run `claude auth login` |
| **Node.js 20+** | Lets Claude scaffold React/Next/Vite projects | https://nodejs.org/ (optional unless you want web-dev) |
| **GitHub CLI** | Lets Claude create new repos for you | https://cli.github.com/ — then run `gh auth login` (optional) |
| **Vercel CLI** | Lets Claude deploy your sites | `npm install -g vercel` (optional) |

Verify each before the next step:

```cmd
conda --version
claude auth status
node --version
gh auth status
```

### Setup the repo

```cmd
git clone https://github.com/iknalos/GujaratiClaude.git
cd GujaratiClaude
setup_text.bat          :: creates gc311 env, installs python data libs (~1 min)
install_shortcut.bat    :: adds "GujaratiClaude" to your Start menu
```

That's it. **Press the Windows key, type "GujaratiClaude", press Enter** to launch.

---

## Daily use

Launch from the Start menu (or double-click `launch_text.bat` from File
Explorer). The dashboard opens with chat on the left, outputs on the
right. Type any Gujarati prompt and press Enter or click **મોકલો** (Send).

### Things to try (all in Gujarati)

| Prompt | What happens |
|---|---|
| `આ ફોલ્ડરમાં કઈ ફાઇલો છે?` | Claude lists your user folder |
| `<path>.xlsx ની data વાંચીને bar chart બનાવો` | Claude reads Excel with pandas, plots, saves PNG → appears in right pane |
| `એક React counter app બનાવો અને localhost પર ચાલુ કરો` | Claude `pnpm create vite`, installs deps, starts dev server, tells you the URL |
| `GitHub પર push કરો` | Claude `git init`, `gh repo create`, `git push` (needs `gh auth login` first) |
| `vercel પર deploy કરો` | Claude links project to Vercel, deploys to production |

### Defaults

- **Working directory:** `%USERPROFILE%` (so Claude can read anywhere
  under your user folder — Desktop, Documents, project folders).
  Override with `launch_text.bat --project-dir C:\specific\folder`.
- **Permission mode:** `bypassPermissions` (Claude runs Bash/Write/Edit
  without per-call prompts — required because the GUI has no approval
  dialog). Override with `set GC_PERMISSION_MODE=acceptEdits` before
  launching.

---

## Architecture

```
┌──────────────────────────┐         ┌──────────────────────────────┐
│  GujaratiClaude (you)    │         │  Claude Code subprocess      │
│                          │  text   │                              │
│  Tk chat (Gujarati) ──── │ ──────► │  claude -p                   │
│                          │  JSON   │  --input-format stream-json  │
│  Outputs panel ◄──────── │ ◄────── │  --output-format stream-json │
│  (watches outputs/)      │  files  │  has Read/Write/Edit/Bash/   │
└──────────────────────────┘         │  Glob/Grep — same as the CLI │
                                     └──────────────────────────────┘
```

A single Python process runs:
- **Tk mainloop** — chat transcript, outputs file list, image preview
- **claude_bridge** — long-lived `claude -p` subprocess, line-buffered JSON
- **outputs_watcher** — 1 Hz poll of `outputs/`, emits new files to the panel
- (voice mode adds: wake-word listener thread, dialog-loop state machine)

All threads communicate through `queue.Queue` (Tkinter isn't thread-safe).

---

## Repo layout

```
GujaratiClaude/
├── main.py                   entrypoint (text & voice modes)
├── gui.py                    unified dashboard (chat + outputs in one window)
├── outputs_panel.py          embedded outputs Frame (file list + preview)
├── outputs_watcher.py        polling thread that watches outputs/
├── claude_bridge.py          persistent claude -p subprocess
├── response_filter.py        sentence buffer (with strip_code toggle)
├── text_mode.py              keyboard driver
├── config.py                 paths + env-overridable settings
├── prompts/
│   ├── gu_system.txt         Gujarati persona + outputs/web-dev conventions
│   ├── gu_reference.wav      (you record) voice clone target for IndicF5
│   └── gu_reference.txt      (you write) transcript of the above
├── outputs/                  (gitignored) Claude saves charts/files here
├── dialog_loop.py            voice-mode state machine (not active in text mode)
├── wake_loop.py              openWakeWord listener (needs trained .onnx)
├── indic_f5_engine.py        IndicF5 TTS engine adapter
├── tools/
│   ├── check_install.py      diagnostic — what's installed, what's missing
│   ├── text_chat.py, stt_smoke.py, tts_smoke.py
│   └── fake_claude.py        test double for the bridge tests
├── tests/                    34 unit tests (31 pass on Windows, 3 hardcode /tmp)
├── setup_text.bat            ⭐ one-time: creates gc311 env + installs python libs
├── launch_text.bat           ⭐ daily: launches the dashboard
├── install_shortcut.bat      ⭐ one-time: adds Start menu entry
├── install.bat               voice mode setup (CUDA PyTorch, Whisper, IndicF5)
├── launch.bat                voice mode launcher
├── PLAN.md                   original design doc
└── README.md
```

---

## Configuration

Override any value in `config.py` with a `GC_<NAME>` environment variable.
The most useful:

| Variable | Default | What it does |
|---|---|---|
| `GC_CLAUDE_BIN` | `claude` | Path to the `claude` executable |
| `GC_PROJECT_DIR` | repo root | Working directory for the subprocess |
| `GC_PERMISSION_MODE` | `bypassPermissions` | `acceptEdits` / `auto` / `bypassPermissions` |
| `GC_WAKE_THRESHOLD` | `0.5` | Wake-word sensitivity (lower = more sensitive) |
| `GC_DIALOG_TIMEOUT_SECS` | `12` | Silence before returning to wake-word listening |

---

## Verifying each piece independently

Run `python tools\check_install.py` first — it tells you what's missing.

| What to test | Command | Expected |
|---|---|---|
| Claude bridge alone | `conda run -n gc311 python main.py --text` | Window opens, type Gujarati, see streamed Gujarati reply |
| Pure-Python logic | `conda run -n gc311 python -m pytest tests/` | 31 pass / 3 fail (POSIX path bugs in Ultraplan's tests) |
| GUI without backends | `python main.py --mock` | Window opens, Wake button cycles colors |
| Whisper STT (voice mode) | `python tools\stt_smoke.py` | Speak Gujarati, see Unicode transcripts |
| IndicF5 TTS (voice mode) | `python tools\tts_smoke.py` | Hear spoken Gujarati; realtime factor < 1.0 |

---

## Voice mode (optional)

Adds Whisper STT + IndicF5 TTS + an openWakeWord listener. **Needs an
NVIDIA GPU** with ≥6 GB VRAM for usable latency.

```cmd
install.bat
```

Then two manual steps:

1. **Train the wake word.** Open the [openWakeWord training Colab](https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb), train "Claude" (~1 hr on free tier), save `.onnx` to `models\claude_wakeword.onnx`.
2. **Record a reference voice.** Drop a 5-10 sec clean Gujarati clip at `prompts\gu_reference.wav` and its transcript at `prompts\gu_reference.txt`. IndicF5 clones this voice.

Launch with `launch.bat`. Say "Claude" → it wakes → speak Gujarati →
Claude replies aloud → 12 s of silence (or say "બંધ કરો") returns to idle.

---

## Status

| Phase | What | Status |
|---|---|---|
| 1 | Skeleton + config + structure | ✅ |
| 2 | Gujarati STT (Whisper-CT2) | ⚠ untested (no GPU on dev machine) |
| 3 | Claude bridge (stream-json) | ✅ E2E verified |
| 3.5 | **Text-mode dashboard** | ✅ **fully usable today, $0 setup** |
| 3.6 | **Outputs panel (charts, Excel, files)** | ✅ |
| 3.7 | **Web-dev workflow (React, GitHub, Vercel)** | ✅ |
| 4 | IndicF5 TTS adapter | ⚠ untested (no GPU) |
| 5 | Wake word | ⚠ needs trained ONNX |
| 6 | Unified single-window GUI | ✅ |
| 7 | Launchers (text + voice + Start menu shortcut) | ✅ |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `claude not on PATH` | Install Claude Code from https://code.claude.com, reopen terminal |
| `claude auth status` non-zero | `claude auth login` |
| `EnvironmentLocationNotFound: gc311` | Run `setup_text.bat` first |
| `Cannot find 'conda'` | Install Miniconda + restart terminal |
| `gh repo create` fails | `gh auth login` (one-time, browser device flow) |
| Bridge says "no response for 10 min" | Claude is genuinely stuck — close and relaunch |
| Outputs panel doesn't update | Click **Refresh**; verify `outputs/` folder exists |
| Gujarati text looks like boxes | Install [Nirmala UI](https://learn.microsoft.com/en-us/typography/font-list/nirmala-ui) font (default on Win10/11) |
| Wake word never fires | Lower threshold: `set GC_WAKE_THRESHOLD=0.35` before launching |

---

## License

MIT. See [`PLAN.md`](PLAN.md) for the original design and library
licenses (faster-whisper MIT, openWakeWord Apache, IndicF5/AI4Bharat
verify before commercial use).
