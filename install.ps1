# install.ps1 — one-line remote installer for GujaratiClaude.
#
# Run via:
#   irm https://raw.githubusercontent.com/iknalos/Gujarati-chat/main/install.ps1 | iex
#
# Or paste into Claude Code: "Run irm https://raw.githubusercontent.com/iknalos/Gujarati-chat/main/install.ps1 | iex"
#
# What it does:
#   1. Installs Git via winget if missing
#   2. Clones (or pulls) iknalos/Gujarati-chat into %USERPROFILE%\Gujarati-chat
#   3. Hands off to bootstrap.ps1 which handles the rest (Miniconda, Node,
#      conda env, deps, tests, webapp launch)

$ErrorActionPreference = "Stop"
# Git and some winget tools write normal progress to stderr. In Windows PowerShell 5.1
# that gets wrapped as a NativeCommandError and halts the script under ErrorActionPreference=Stop.
# Tell PowerShell to treat native-command stderr as plain output, not errors.
$PSNativeCommandUseErrorActionPreference = $false

Write-Host ""
Write-Host -ForegroundColor Cyan "==========================================="
Write-Host -ForegroundColor Cyan "  GujaratiClaude — remote installer"
Write-Host -ForegroundColor Cyan "==========================================="
Write-Host ""

function RefreshPath {
    $env:Path = `
        [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
        [System.Environment]::GetEnvironmentVariable("Path", "User")
}

# -------- Step 1: Git --------------------------------------------------------
if (Get-Command git -ErrorAction SilentlyContinue) {
    Write-Host -ForegroundColor Green ("[1/3] Git found: " + (git --version))
} else {
    Write-Host -ForegroundColor Yellow "[1/3] Git not found — installing via winget..."
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host -ForegroundColor Red "winget is unavailable. Install Git manually from https://git-scm.com and re-run."
        exit 1
    }
    & winget install --id Git.Git --silent --accept-package-agreements --accept-source-agreements | Out-Host
    RefreshPath
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host -ForegroundColor Red "Git install reported success but 'git' is not on PATH. Open a new terminal and re-run this command."
        exit 1
    }
    Write-Host -ForegroundColor Green ("Git installed: " + (git --version))
}

# -------- Step 2: Clone or pull ----------------------------------------------
$Target = Join-Path $env:USERPROFILE "Gujarati-chat"
if (Test-Path (Join-Path $Target ".git")) {
    Write-Host -ForegroundColor Green "[2/3] Repo already at $Target — pulling latest..."
    Push-Location $Target
    try { & git pull --ff-only | Out-Host } catch { }
    Pop-Location
} else {
    Write-Host -ForegroundColor Yellow "[2/3] Cloning into $Target..."
    & git clone https://github.com/iknalos/Gujarati-chat.git $Target | Out-Host
    if (-not (Test-Path (Join-Path $Target ".git"))) {
        Write-Host -ForegroundColor Red "Clone failed — see error above."
        exit 1
    }
    Write-Host -ForegroundColor Green "Cloned to $Target"
}

# -------- Step 3: Hand off to bootstrap.ps1 ----------------------------------
$Bootstrap = Join-Path $Target "bootstrap.ps1"
if (-not (Test-Path $Bootstrap)) {
    Write-Host -ForegroundColor Red "bootstrap.ps1 not found in cloned repo — the repo on GitHub may be out of date."
    exit 1
}

Write-Host -ForegroundColor Cyan "[3/3] Handing off to bootstrap.ps1 (installs conda/node/python-deps, runs tests, launches webapp)"
Write-Host ""
Set-Location $Target
& powershell -ExecutionPolicy Bypass -NoProfile -File $Bootstrap

