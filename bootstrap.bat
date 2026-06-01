@echo off
REM Double-clickable entry point for bootstrap.ps1.
REM Runs PowerShell with ExecutionPolicy Bypass so the script isn't blocked
REM by per-machine policy. No admin required (winget elevates only the
REM specific installer commands that need it).

set "REPO_DIR=%~dp0"
if "%REPO_DIR:~-1%"=="\" set "REPO_DIR=%REPO_DIR:~0,-1%"

powershell -ExecutionPolicy Bypass -NoProfile -File "%REPO_DIR%\bootstrap.ps1"
if errorlevel 1 (
    echo.
    echo Bootstrap reported a failure. See output above and INSTALL.md.
    pause
    exit /b 1
)
pause
