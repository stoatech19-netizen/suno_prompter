@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Setup has not been run yet. Please double-click setup.bat first.
    pause
    exit /b 1
)

if not exist ".env" (
    echo [ERROR] .env file not found. Copy .env.example to .env and add your Gemini API key first.
    pause
    exit /b 1
)

set "HAS_KEY="
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if /i "%%A"=="GEMINI_API_KEY" for %%C in (%%B) do set "HAS_KEY=1"
    if /i "%%A"=="GEMINI_API_KEYS" for %%C in (%%B) do set "HAS_KEY=1"
)
if not defined HAS_KEY (
    echo [ERROR] No Gemini API key found in .env yet.
    echo Open the .env file in this folder with Notepad and add your key, e.g.:
    echo     GEMINI_API_KEY=your-key-here
    echo Don't have one? Get a free key at: https://aistudio.google.com/apikey
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
