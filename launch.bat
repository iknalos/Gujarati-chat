@echo off
REM GujaratiClaude launcher. Pass --project-dir <path> to point Claude at
REM a specific working directory (defaults to this repo). Pass --no-wake to
REM skip the wake-word listener and trigger conversations manually via the
REM GUI "Wake" button.

setlocal
cd /d "%~dp0"
call venv\Scripts\activate.bat || goto :error
python main.py %*
exit /b %errorlevel%

:error
echo Could not activate the venv. Run install.bat first.
exit /b 1
