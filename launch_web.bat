@echo off
REM Launch GujaratiClaude in webapp mode (FastAPI + pywebview).
REM Uses gc311's pythonw.exe so there's no console window — only the
REM dashboard window. The webapp is served on localhost and rendered
REM inside a native window via pywebview.

setlocal
set "REPO_DIR=%~dp0"
if "%REPO_DIR:~-1%"=="\" set "REPO_DIR=%REPO_DIR:~0,-1%"
set "PYTHONW=%USERPROFILE%\.conda\envs\gc311\pythonw.exe"

REM Default project-dir to USERPROFILE if not given
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

start "" "%PYTHONW%" "%REPO_DIR%\main.py" --web %EXTRA_ARGS% %*
