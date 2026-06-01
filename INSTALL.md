# Installing GujaratiClaude on a fresh Windows machine

This guide walks through getting the webapp running on a clean Windows 10
or 11 machine. The **fast path** is one command (`bootstrap.bat`). The
manual sections below explain what each step does so you can debug if
anything goes wrong.

---

## TL;DR — fast path (5 minutes)

**Prerequisites already on the machine:**
- Windows 10 (1809+) or Windows 11
- [Claude Code](https://code.claude.com) installed AND authenticated (`claude auth login` done once)

**Steps:**

1. Open PowerShell, navigate where you want the repo, and clone:
   ```powershell
   git clone https://github.com/iknalos/Gujarati-chat.git
   cd Gujarati-chat
   ```
   *(If `git` isn't installed: download from https://git-scm.com — or skip this and let bootstrap.ps1 install it via winget after you grab the zip from GitHub.)*

2. Double-click **`bootstrap.bat`** in File Explorer, OR run:
   ```powershell
   powershell -ExecutionPolicy Bypass -File bootstrap.ps1
   ```

3. The script:
   - Detects what's missing
   - `winget install`s anything missing (Git, Miniconda, Node.js)
   - Creates the `gc311` Python 3.11 env
   - Installs all Python deps
   - Runs the test suite
   - Launches the webapp
   - Waits for `localhost:5174` to respond
   - Prints **READY — GujaratiClaude webapp is running**

4. The pywebview window opens. Type Gujarati and chat.

If at any point it fails, scroll back through the output — every step is labeled `[N/9]` with a clear OK / WARN / FAIL. The script is idempotent; re-running it after fixing the issue picks up from where it stopped.

---

## What the bootstrap does (and what to do if it fails)

### Step 1 — Git

```
[1/9] Checking Git
```

- Runs `git --version`. If present: skip.
- If missing: `winget install --id Git.Git`

**Manual fix:** download the Git for Windows installer from https://git-scm.com/download/win and run it. Default options are fine. Open a new terminal.

### Step 2 — Miniconda / Anaconda

```
[2/9] Checking Miniconda / Anaconda
```

- Runs `conda --version`. If present: skip.
- If missing: `winget install --id Anaconda.Miniconda3`

**Manual fix:** download Miniconda from https://docs.conda.io/en/latest/miniconda.html and run the installer. **Check "Add Miniconda3 to my PATH environment variable"** on the install options screen (otherwise `conda` won't be findable from arbitrary shells).

### Step 3 — Node.js

```
[3/9] Checking Node.js (for web-dev workflow)
```

Optional but recommended — without Node, Claude can't scaffold React/Next apps for you. If missing: `winget install --id OpenJS.NodeJS.LTS`.

**Manual fix:** https://nodejs.org → LTS installer.

### Step 4 — Claude Code CLI

```
[4/9] Checking Claude Code CLI
```

- Verifies `claude --version` works AND `claude auth status` returns 0.
- If missing: prints instructions and **stops**. You need to install Claude Code yourself from https://code.claude.com, then run `claude auth login` once (browser device flow, ~30 seconds), then re-run `bootstrap.bat`.

### Step 5 — Optional tools

```
[5/9] Checking optional tools (gh, vercel)
```

- **gh CLI** (`gh`): needed only if you want Claude to create new GitHub repos for you. Install: `winget install GitHub.cli`, then `gh auth login`.
- **vercel** is installed later via npm when you need to deploy a site. Not a hard requirement.

### Step 6 — Create gc311 conda env

```
[6/9] Creating gc311 conda env (Python 3.11)
```

The webapp needs Python 3.11 with several packages. We use a dedicated conda env so it doesn't touch your system Python.

If `gc311` already exists, this step skips. If it doesn't, runs:
```
conda create -n gc311 python=3.11 -y
```

**Manual fix:** open Anaconda Prompt and run the same command. If it complains about already existing, that's fine.

### Step 7 — Install Python deps

```
[7/9] Installing Python deps into gc311
```

Installs into the `gc311` env:

| Package | Why |
|---|---|
| `pillow` | Image preview in outputs pane |
| `matplotlib` | Claude uses this to make charts |
| `pandas` | Claude uses this for Excel / CSV |
| `numpy<2` | matplotlib was compiled against numpy 1.x |
| `openpyxl` | Excel reading |
| `pytest` | Test suite |
| `fastapi` | Web server |
| `uvicorn[standard]` | ASGI runner |
| `pywebview` | Native window wrapper around the local URL |
| `sv-ttk` | Modern theme for legacy Tk fallback |
| `tkinterweb` | HTML preview for legacy Tk fallback |

After install, runs an `import` check to confirm all required packages are loadable.

**Manual fix:**
```
conda run -n gc311 --no-capture-output pip install pillow matplotlib pandas "numpy<2" openpyxl pytest fastapi "uvicorn[standard]" pywebview sv-ttk tkinterweb
```

### Step 8 — Unit tests

```
[8/9] Running unit tests
```

Runs `pytest tests/`. Expect **31 pass / 3 fail**. The 3 failures hardcode the POSIX path `/tmp` (carryover from Ultraplan's tests) and only fail on Windows — they're not real bugs. The script treats this as acceptable.

If you see fewer than 31 passing, something is wrong with the package install — re-run step 7.

### Step 9 — Launch webapp

```
[9/9] Launching the webapp
```

Launches `pythonw.exe main.py --web --project-dir %USERPROFILE%` (no console window), waits up to 25 s for `localhost:5174` (or 5175..5180) to respond with our HTML, then prints:

```
============================================================
READY — GujaratiClaude webapp is running.
URL: http://127.0.0.1:5174
============================================================
```

A native pywebview window also opens to that URL.

**If the server doesn't respond:**
- Check `.web_stderr.log` in the repo for any traceback.
- Run the launch command manually so you can see live output:
  ```
  & "$env:USERPROFILE\.conda\envs\gc311\pythonw.exe" main.py --web --project-dir "$env:USERPROFILE"
  ```
- Confirm no firewall is blocking localhost.

---

## What to do after READY

1. The pywebview window should be open. If you don't see it, alt-tab.
2. Try a Gujarati prompt: `નમસ્તે, તું શું કરી શકે?`
3. Drag a file onto the chat or click 📎 to attach it; Claude reads it via its Read tool.
4. Files Claude creates land in `outputs/` and appear in the right pane with inline preview (PNG, HTML, SVG, CSV, text).

**Daily-use launchers** (after bootstrap.bat has run once):
- `launch_web.bat` — opens the webapp (fastest path going forward)
- `launch_text.bat` — opens the legacy Tk dashboard (fallback)
- `install_shortcut.bat` — adds a Start-menu shortcut so you can launch from Windows search

---

## Verifying a setup without installing anything

If you've already run bootstrap.bat once and want to check that everything is still in working order, run:
```powershell
conda run -n gc311 --no-capture-output python tools\check_install.py
```

That diagnoses missing pieces without trying to install anything.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `winget` not found | Update App Installer from the Microsoft Store. Win10 1809+ ships with winget. |
| `conda` not on PATH after install | Open a NEW terminal (winget's PATH update doesn't reach the running shell). Or use "Anaconda Prompt" from the Start menu. |
| `claude auth status` fails | Run `claude auth login`, follow the browser device flow. |
| pywebview window doesn't open | Check `.web_stderr.log`. Try running with regular `python` (not `pythonw`) to see live errors. |
| "credential selector" dialog when pushing to git | See the README — it's a duplicate `[credential]` entry in `~/.gitconfig`. |
| Webapp shows the wrong app (counter-app etc.) | Browser cache. Hard-refresh (Ctrl+F5) or use an Incognito window. |
| Port 5174 already in use | The launcher tries 5174..5180 automatically. Kill anything else listening on those (`netstat -ano \| findstr :5174`). |

---

## Bootstrapping without admin / on a locked-down machine

If you can't run winget (corporate-locked machine, no admin):
1. Manually install each tool yourself from the official source (links above).
2. Then run `bootstrap.ps1` — it'll detect each tool is present and skip ahead, only doing the env creation + dep install steps (which don't need admin).

The conda env creation and `pip install`s all happen in user space (`%USERPROFILE%\.conda\envs\gc311\`) — no admin needed.

---

## What gets stored on disk after install

| Path | What |
|---|---|
| `%USERPROFILE%\Gujarati-chat\` (or wherever you cloned) | The repo itself |
| `%USERPROFILE%\.conda\envs\gc311\` | Isolated Python 3.11 + all deps (~600 MB) |
| `%USERPROFILE%\.gujarati_claude_history.json` | Persisted chat transcript + Claude session ID |
| `<repo>\outputs\` | Charts / HTML / data files Claude creates (gitignored) |
| `%USERPROFILE%\.claude\` | Claude Code's own state (sessions, settings, MCP config) |

Nothing else. To uninstall completely: `conda env remove -n gc311`, delete the repo folder, delete the history file. Claude Code itself is uninstalled separately via its own installer.
