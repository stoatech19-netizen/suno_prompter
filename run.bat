@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Setup has not been run yet. Please double-click setup.bat first.
    pause
    exit /b 1
)

echo Starting Suno Prompt Generator...
echo Your browser will open automatically in a moment.
echo Close this window to stop the server.
echo.

start "" cmd /c "timeout /t 2 >nul && start http://127.0.0.1:5001"
".venv\Scripts\python.exe" app.py

pause
