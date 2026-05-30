@echo off
REM One-time setup for text-mode GujaratiClaude (no voice deps).
REM Creates a conda env "gc311" with Python 3.11 and installs the
REM Python data/visualisation libraries Claude will use via Bash.
REM
REM Requires: Miniconda or Anaconda already installed and `conda`
REM available on PATH, plus Claude Code (`claude` CLI) authenticated.

setlocal

where conda >nul 2>&1
if errorlevel 1 (
    echo ERROR: `conda` not found on PATH.
    echo Install Miniconda from https://docs.conda.io/en/latest/miniconda.html
    exit /b 1
)

where claude >nul 2>&1
if errorlevel 1 (
    echo WARNING: `claude` not found on PATH.
    echo Install Claude Code from https://code.claude.com and run `claude auth login`.
)

echo Creating conda env "gc311" with Python 3.11...
call conda create -n gc311 python=3.11 -y || exit /b 1

echo Installing Python data libs into gc311...
call conda run -n gc311 --no-capture-output pip install --quiet ^
    pillow matplotlib pandas "numpy<2" openpyxl pytest || exit /b 1

echo.
echo ============================================================
echo Setup complete.
echo Run launch_text.bat to start the dashboard.
echo (Tip: also run `claude auth status` to confirm Claude is logged in,
echo  and `gh auth login` if you want Claude to create GitHub repos.)
echo ============================================================
pause
