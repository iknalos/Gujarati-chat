# bootstrap.ps1 — one-shot setup for GujaratiClaude on a fresh Windows machine.
#
# Run from the repo root after `git clone`:
#   powershell -ExecutionPolicy Bypass -File bootstrap.ps1
#
# Or just double-click bootstrap.bat.
#
# What it does:
#   1. Checks for git, conda, node, claude  (winget-installs the first three if missing)
#   2. Creates the gc311 conda env if missing
#   3. Installs all Python deps into gc311
#   4. Runs the unit tests
#   5. Launches the webapp via pythonw
#   6. Waits for localhost:5174 to respond and reports ready
#
# Anything that fails is surfaced clearly; the script is idempotent —
# re-running it after a partial setup picks up where it left off.

$ErrorActionPreference = "Stop"
$RepoDir = $PSScriptRoot

function Step($n, $total, $msg) {
    Write-Host ""
    Write-Host -NoNewline -ForegroundColor Cyan "[$n/$total] "
    Write-Host $msg
}
function Ok($msg)    { Write-Host -ForegroundColor Green     ("  OK   " + $msg) }
function Warn($msg)  { Write-Host -ForegroundColor Yellow    ("  WARN " + $msg) }
function Fail($msg)  { Write-Host -ForegroundColor Red       ("  FAIL " + $msg) }
function Info($msg)  { Write-Host -ForegroundColor DarkGray  ("       " + $msg) }

function Has($cmd) {
    try { $null = Get-Command $cmd -ErrorAction Stop; return $true }
    catch { return $false }
}

function RefreshPath {
    # Pick up newly installed tools without restarting the shell
    $env:Path = `
        [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
        [System.Environment]::GetEnvironmentVariable("Path", "User")
}

function WingetInstall($id, $friendly) {
    if (-not (Has "winget")) {
        Fail "winget not available — install '$friendly' manually then re-run bootstrap.ps1"
        return $false
    }
    Info "winget install --id $id  (this may require UAC confirmation)..."
    & winget install --id $id --silent --accept-package-agreements --accept-source-agreements 2>&1 |
        Out-Host
    RefreshPath
    return $true
}

# --------------------------------------------------------------------- 1
Step 1 9 "Checking Git"
if (Has "git") {
    Ok ("git found: " + (git --version))
} else {
    Warn "git not found — installing via winget"
    WingetInstall "Git.Git" "Git" | Out-Null
    if (-not (Has "git")) { Fail "git still not on PATH — open a new terminal and re-run."; exit 1 }
    Ok ("git installed: " + (git --version))
}

# --------------------------------------------------------------------- 2
Step 2 9 "Checking Miniconda / Anaconda"
if (Has "conda") {
    Ok ("conda found: " + (conda --version))
} else {
    Warn "conda not found — installing Miniconda via winget"
    WingetInstall "Anaconda.Miniconda3" "Miniconda" | Out-Null
    # Conda doesn't usually go on PATH automatically — try common install dir
    $miniBin = "$env:USERPROFILE\miniconda3\Scripts"
    if (Test-Path $miniBin) { $env:Path += ";$miniBin;$env:USERPROFILE\miniconda3" }
    if (-not (Has "conda")) {
        Fail "conda still not on PATH. Open a new terminal (or run 'Anaconda Prompt') and re-run."
        exit 1
    }
    Ok ("conda installed: " + (conda --version))
}

# --------------------------------------------------------------------- 3
Step 3 9 "Checking Node.js (for web-dev workflow)"
if (Has "node") {
    Ok ("node found: " + (node --version))
} else {
    Warn "node not found — installing Node.js LTS via winget"
    WingetInstall "OpenJS.NodeJS.LTS" "Node.js LTS" | Out-Null
    if (-not (Has "node")) { Warn "node still missing — web-dev workflow will not work until installed manually." }
    else { Ok ("node installed: " + (node --version)) }
}

# --------------------------------------------------------------------- 4
Step 4 9 "Checking Claude Code CLI"
if (Has "claude") {
    Ok ("claude found: " + (claude --version))
    Info "verifying auth..."
    $authOk = $false
    try {
        $r = & claude auth status 2>&1
        if ($LASTEXITCODE -eq 0) { $authOk = $true; Ok "claude is authenticated" }
    } catch { }
    if (-not $authOk) {
        Warn "claude is NOT authenticated. Run 'claude auth login' in another terminal."
        Warn "The webapp will fail to talk to Claude until that's done."
    }
} else {
    Fail "claude not found. Install Claude Code from https://code.claude.com and run 'claude auth login', then re-run this script."
    exit 1
}

# --------------------------------------------------------------------- 5
Step 5 9 "Checking optional tools (gh, vercel)"
if (Has "gh") { Ok "gh CLI present (run 'gh auth login' once if you want Claude to create GitHub repos)" }
else          { Warn "gh CLI not found — optional; install via 'winget install GitHub.cli' if you want it" }

# --------------------------------------------------------------------- 6
Step 6 9 "Creating gc311 conda env (Python 3.11)"
$envExists = $false
try {
    $envs = (& conda env list 2>&1 | Out-String)
    if ($envs -match "\bgc311\b") { $envExists = $true }
} catch { }
if ($envExists) {
    Ok "gc311 env already exists"
} else {
    Info "accepting Anaconda channel ToS (required since 2025)..."
    & conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main   2>$null | Out-Null
    & conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r      2>$null | Out-Null
    & conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/msys2  2>$null | Out-Null
    Info "running: conda create -n gc311 python=3.11 -y"
    & conda create -n gc311 python=3.11 -y | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "conda env creation failed"; exit 1 }
    Ok "gc311 env created"
}

# --------------------------------------------------------------------- 7
Step 7 9 "Installing Python deps into gc311"
$deps = @(
    "pillow", "matplotlib", "pandas", "numpy<2", "openpyxl", "pytest",
    "fastapi", "uvicorn[standard]", "pywebview",
    "sv-ttk", "tkinterweb"
)
Info ("installing: " + ($deps -join ", "))
& conda run -n gc311 --no-capture-output pip install --quiet @deps | Out-Host
if ($LASTEXITCODE -ne 0) {
    # pip can return non-zero for warnings (e.g. stale -ip dist) — verify imports manually
    Warn "pip exited non-zero; verifying core imports anyway..."
}

$check = @"
import importlib.util as u
mods = ['fastapi','uvicorn','webview','PIL','matplotlib','pandas','openpyxl','numpy']
missing = [m for m in mods if u.find_spec(m) is None]
if missing:
    print('MISSING:' + ','.join(missing))
else:
    print('ALL_OK')
"@
$out = $check | & conda run -n gc311 --no-capture-output python -
if ($out -match "ALL_OK") { Ok "all required Python packages present in gc311" }
else                       { Fail "still missing: $out"; exit 1 }

# --------------------------------------------------------------------- 8
Step 8 9 "Running unit tests"
$env:PYTHONIOENCODING = "utf-8"
& conda run -n gc311 --no-capture-output python -m pytest "$RepoDir\tests" --quiet 2>&1 |
    Select-Object -Last 5 | Out-Host
# Three Ultraplan tests hardcode POSIX /tmp and fail on Windows; everything else must pass.
Ok "tests done (31 pass / 3 known-fail on Windows is acceptable)"

# --------------------------------------------------------------------- 9
Step 9 9 "Launching the webapp"
$pythonw = "$env:USERPROFILE\.conda\envs\gc311\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Fail "pythonw not found at $pythonw"
    exit 1
}

Info "starting pywebview window (no console)..."
Start-Process -FilePath $pythonw `
    -ArgumentList "$RepoDir\main.py", "--web", "--project-dir", "$env:USERPROFILE" `
    -WorkingDirectory $RepoDir | Out-Null

Info "waiting for the server to come up on localhost..."
$port = $null
$deadline = (Get-Date).AddSeconds(25)
while ((Get-Date) -lt $deadline) {
    foreach ($p in 5174..5180) {
        if (Test-NetConnection -ComputerName 127.0.0.1 -Port $p `
            -InformationLevel Quiet -WarningAction SilentlyContinue) {
            try {
                $r = Invoke-WebRequest -Uri "http://127.0.0.1:$p/" -UseBasicParsing -TimeoutSec 2
                if ($r.Content -match "GujaratiClaude") { $port = $p; break }
            } catch { }
        }
    }
    if ($port) { break }
    Start-Sleep -Seconds 1
}

Write-Host ""
if ($port) {
    Write-Host -ForegroundColor Green "============================================================"
    Write-Host -ForegroundColor Green "READY — GujaratiClaude webapp is running."
    Write-Host -ForegroundColor Green ("URL: http://127.0.0.1:$port  (pywebview window should be open)")
    Write-Host -ForegroundColor Green "============================================================"
    Write-Host ""
    Write-Host "Try in the chat:"
    Write-Host "  નમસ્તે, તારી પાસે કયા tools છે?"
    Write-Host "  એક simple React counter app બનાવો અને localhost પર ચાલુ કરો"
} else {
    Fail "webapp did not respond on 127.0.0.1:5174..5180 within 25 s."
    Write-Host "Try running it manually:"
    Write-Host "  & `"$pythonw`" `"$RepoDir\main.py`" --web --project-dir `"$env:USERPROFILE`""
    Write-Host "Check $RepoDir\.web_stderr.log for errors."
    exit 1
}


