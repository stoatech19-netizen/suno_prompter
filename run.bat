@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Setup has not been run yet. Please double-click setup.bat first.
    pause
    exit /b 1
)

if exist ".git" (
    echo Checking for updates...
    git fetch --quiet origin main >nul 2>nul
    if !errorlevel! equ 0 (
        for /f "delims=" %%H in ('git rev-parse HEAD') do set "LOCAL_HEAD=%%H"
        for /f "delims=" %%H in ('git rev-parse origin/main') do set "REMOTE_HEAD=%%H"
        if not "!LOCAL_HEAD!"=="!REMOTE_HEAD!" (
            echo [INFO] Update found. Applying...
            git diff --quiet HEAD origin/main -- requirements.txt
            set "REQS_CHANGED=!errorlevel!"
            git pull --ff-only origin main
            if !errorlevel! equ 0 (
                if not "!REQS_CHANGED!"=="0" (
                    echo [INFO] Dependencies changed, reinstalling...
                    ".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt
                )
                echo [OK] Updated to the latest version.
            ) else (
                echo [WARN] Could not apply the update automatically ^(local changes in this folder?^). Continuing with the current version.
            )
        )
    ) else (
        echo [WARN] Could not check for updates ^(offline?^). Continuing with the current version.
    )
    echo.
)

echo Starting Suno Prompt Generator...
echo Your browser will open automatically in a moment.
echo Close this window to stop the server.
echo.

start "" cmd /c "timeout /t 2 >nul && start http://127.0.0.1:5001"
".venv\Scripts\python.exe" app.py

pause
