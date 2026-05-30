@echo off
REM Launch GujaratiClaude in text mode (no voice deps required).
REM Uses the gc311 conda env created by setup_text.bat.
REM
REM Default project dir is your user folder (%USERPROFILE%), so Claude
REM can read/write anywhere under it including Desktop, project folders,
REM etc. Override with: launch_text.bat --project-dir C:\some\folder

setlocal
set "REPO_DIR=%~dp0"
if "%REPO_DIR:~-1%"=="\" set "REPO_DIR=%REPO_DIR:~0,-1%"

REM Pass through any extra args; default --project-dir if none given.
echo %* | findstr /C:"--project-dir" >nul
if errorlevel 1 (
    set "EXTRA_ARGS=--project-dir %USERPROFILE%"
) else (
    set "EXTRA_ARGS="
)

conda run -n gc311 --no-capture-output python "%REPO_DIR%\main.py" --text %EXTRA_ARGS% %*
if errorlevel 1 (
    echo.
    echo Launch failed. If you see "EnvironmentLocationNotFound" or "No env named gc311",
    echo run setup_text.bat first.
    pause
    exit /b 1
)
