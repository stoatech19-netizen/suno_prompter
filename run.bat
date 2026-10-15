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

rem A previous instance can be left listening on 5001 if it didn't shut
rem down cleanly (crash, older version without the auto-stop heartbeat,
rem etc). If we don't clear it, the new process below fails to bind to
rem the port and exits immediately (invisibly, since this window is
rem hidden by launch.vbs) -- the browser then just reopens the OLD
rem process, and it looks like the update never applied. Force-killing
rem whatever's on 5001 first makes every launch start from a clean,
rem up-to-date process.
for /f "tokens=5" %%P in ('netstat -ano ^| findstr "127.0.0.1:5001" ^| findstr "LISTENING"') do (
    echo [INFO] Stopping a previous server instance ^(PID %%P^)...
    taskkill /F /PID %%P >nul 2>nul
)

echo Starting Suno Prompt Generator...
echo Your browser will open automatically in a moment.
echo Close this window to stop the server.
echo.

start /b "" cmd /c "timeout /t 2 >nul && start http://127.0.0.1:5001"
".venv\Scripts\python.exe" app.py

if errorlevel 1 (
    echo.
    echo [ERROR] The server stopped unexpectedly ^(exit code %errorlevel%^).
    pause
)
