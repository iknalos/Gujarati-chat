@echo off
REM Launch GujaratiClaude in text mode (no voice deps required).
REM Uses gc311's pythonw.exe directly so there's no console window — only
REM the dashboard. This avoids the "minimize / close the parent terminal
REM also kills the app" footgun.
REM
REM Default project dir is your user folder, so Claude can read/write
REM anywhere under it including Desktop, project folders, etc. Override
REM with: launch_text.bat --project-dir C:\some\folder

setlocal
set "REPO_DIR=%~dp0"
if "%REPO_DIR:~-1%"=="\" set "REPO_DIR=%REPO_DIR:~0,-1%"
set "PYTHONW=%USERPROFILE%\.conda\envs\gc311\pythonw.exe"

REM Pass --project-dir defaulting to USERPROFILE if user didn't supply one
echo %* | findstr /C:"--project-dir" >nul
if errorlevel 1 (
    set "EXTRA_ARGS=--project-dir %USERPROFILE%"
) else (
    set "EXTRA_ARGS="
)

if not exist "%PYTHONW%" (
    echo gc311 env not found at %PYTHONW%
    echo Run setup_text.bat first to create it.
    pause
    exit /b 1
)

REM Detached, no console — closing this .bat window cannot kill the GUI.
start "" "%PYTHONW%" "%REPO_DIR%\main.py" --text %EXTRA_ARGS% %*
