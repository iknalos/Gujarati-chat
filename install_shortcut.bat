@echo off
REM Create a Windows Start-menu shortcut to launch GujaratiClaude.
REM After running this once, press the Windows key, type "GujaratiClaude",
REM and hit Enter to launch the dashboard.

setlocal
set "REPO_DIR=%~dp0"
if "%REPO_DIR:~-1%"=="\" set "REPO_DIR=%REPO_DIR:~0,-1%"

set "LNK_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\GujaratiClaude.lnk"

powershell -NoProfile -Command ^
  "$w = New-Object -ComObject WScript.Shell;" ^
  "$l = $w.CreateShortcut('%LNK_PATH%');" ^
  "$l.TargetPath = '%REPO_DIR%\launch_text.bat';" ^
  "$l.WorkingDirectory = '%REPO_DIR%';" ^
  "$l.Description = 'Gujarati interface for Claude Code (text mode dashboard)';" ^
  "$l.Save()"

if exist "%LNK_PATH%" (
    echo.
    echo Shortcut created:
    echo   %LNK_PATH%
    echo.
    echo Press the Windows key, type "GujaratiClaude", press Enter.
) else (
    echo ERROR: shortcut creation failed.
    exit /b 1
)
pause
